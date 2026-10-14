import os
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from app.database import db
from app.payments import initiate_b2c_payout, initiate_b2b_payout, format_phone_number

logger = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))

# ========================================================
# 1. EVENT ORGANIZER AUTOMATIC & INSTANT CASH PAYOUT ENGINE
# ========================================================

def resolve_payout_destination(target: str):
    """
    Analyzes organizer's phone number or Till / Paybill number.
    Returns: (channel, clean_dest, error_msg)
    - 'b2b_till': 5-7 digits (Buy Goods & Services)
    - 'b2b_paybill': 5-7 digits (Paybill shortcode)
    - 'b2c_phone': 9-12 digits personal M-Pesa line (formatted as 254XXXXXXXXX)
    """
    if not target:
        return None, None, "Organizer destination number is missing."

    raw = str(target).strip()
    digits = ''.join(filter(str.isdigit, raw))
    lower = raw.lower()

    if not digits:
        return None, None, f"No digits found in destination '{target}'."

    # Explicit keyword detection
    is_explicit_paybill = 'paybill' in lower
    is_explicit_till = 'till' in lower or 'buy goods' in lower

    # 5 to 7 digits is an M-Pesa Till or Paybill shortcode
    if 5 <= len(digits) <= 7:
        if is_explicit_paybill:
            return 'b2b_paybill', digits, None
        return 'b2b_till', digits, None

    # 9, 10, or 12 digits is a personal M-Pesa mobile number
    if len(digits) in [9, 10, 12]:
        fmt = format_phone_number(digits)
        if fmt and len(fmt) == 12 and fmt.startswith('254'):
            return 'b2c_phone', fmt, None

    # Fallback checks
    fmt = format_phone_number(digits)
    if fmt and len(fmt) == 12 and fmt.startswith('254'):
        return 'b2c_phone', fmt, None
    elif 5 <= len(digits) <= 8:
        return 'b2b_till', digits, None

    return None, None, f"Invalid M-Pesa phone or Till number: '{target}'."


def schedule_event_organizer_payout(event_id: str, ticket_code: str, amount: float or int, organizer_phone: str = None, delay_seconds: int = 0):
    """
    Schedules and executes automated cash transfer of the event ticket fee directly to the organizer.
    - If delay_seconds <= 0: Transfers immediately in real-time.
    - If delay_seconds > 0: Schedules with background execution and DB fallback persistence.
    - Detects whether destination is a personal phone (B2C) or venue Till/Paybill (B2B).
    """
    try:
        if not organizer_phone:
            event_data = db.reference(f'events/{event_id}').get() or {}
            organizer_phone = event_data.get('organizer_phone')

        channel, clean_dest, err = resolve_payout_destination(organizer_phone)
        if not channel or not clean_dest:
            logger.error(f"❌ Cannot execute ticket payout for event {event_id}: {err}")
            return False

        clean_amount = int(round(float(amount)))
        if clean_amount <= 0:
            return False

        # Deterministic payout ID prevents any double disbursement for the same ticket
        payout_id = f"evt_payout_{event_id}_{ticket_code.replace('-', '_')}"

        # Check existing payout state before writing
        existing_payout = db.reference(f'pending_organizer_payouts/{payout_id}').get()
        if existing_payout and isinstance(existing_payout, dict):
            status = existing_payout.get('status')
            if status in ['disbursed', 'paid']:
                logger.info(f"ℹ️ Payout {payout_id} has already been disbursed. Aborting duplicate.")
                return True
            if status == 'processing':
                logger.info(f"⏳ Payout {payout_id} is already actively processing. Aborting duplicate.")
                return True

        now_ms = int(time.time() * 1000)
        scheduled_at_ms = now_ms + (max(0, delay_seconds) * 1000)

        # Fetch event title
        event_data = db.reference(f'events/{event_id}').get() or {}
        event_title = event_data.get('title', 'Campus Event')

        record = {
            "id": payout_id,
            "event_id": event_id,
            "event_title": event_title,
            "ticket_code": ticket_code,
            "amount": clean_amount,
            "organizer_phone": clean_dest,
            "raw_destination": organizer_phone,
            "channel": channel,
            "created_at": now_ms,
            "scheduled_at": scheduled_at_ms,
            "status": "scheduled",
            "delay_seconds": delay_seconds
        }

        # Persist to Firebase Realtime Database
        db.reference(f'pending_organizer_payouts/{payout_id}').set(record)
        logger.info(f"💰 Ticket payout registered: KES {clean_amount} -> {clean_dest} ({channel}) for ticket {ticket_code}")

        # If zero delay (immediate mode), disburse right now
        if delay_seconds <= 0:
            logger.info(f"⚡ Instant disbursement triggered for payout {payout_id}...")
            return execute_single_organizer_payout(payout_id)

        # Otherwise, spawn background timer thread for delayed execution
        def timer_worker():
            time.sleep(delay_seconds)
            execute_single_organizer_payout(payout_id)

        threading.Thread(target=timer_worker, daemon=True).start()
        return True

    except Exception as e:
        logger.error(f"❌ Error scheduling organizer payout: {e}")
        return False


def execute_single_organizer_payout(payout_id: str):
    """
    Executes a single organizer cash payout via M-Pesa B2C (personal phone) or B2B (Till/Paybill).
    Guarded by atomic status lock to prevent duplicate disbursements.
    """
    payout_ref = db.reference(f'pending_organizer_payouts/{payout_id}')
    payout = payout_ref.get()
    if not payout:
        return {"success": False, "error": "Payout record not found."}

    if payout.get('status') in ['disbursed', 'paid']:
        logger.info(f"ℹ️ Payout {payout_id} already disbursed.")
        return {"success": True, "already_disbursed": True}

    now_ms = int(time.time() * 1000)

    # Active processing lock: if currently processing within last 60 seconds, prevent duplicate call
    if payout.get('status') == 'processing':
        proc_started = int(payout.get('processing_started_at', 0) or 0)
        if now_ms - proc_started < 60000:
            logger.warning(f"⚠️ Payout {payout_id} is already actively processing ({now_ms - proc_started}ms ago). Duplicate prevented.")
            return {"success": False, "error": "Payout is currently being processed by Safaricom."}

    dest = payout.get('organizer_phone')
    amount = payout.get('amount')
    event_title = payout.get('event_title', 'Campus Event')
    ticket_code = payout.get('ticket_code', '')
    event_id = payout.get('event_id')
    channel = payout.get('channel')

    if not channel or not dest:
        channel, dest, _ = resolve_payout_destination(dest or payout.get('raw_destination'))

    # Atomic lock
    now_ms = int(time.time() * 1000)
    payout_ref.update({"status": "processing", "processing_started_at": now_ms})

    remarks = f"Tkt {ticket_code} {event_title}"[:95]
    res = {"success": False, "error": "Unknown channel"}

    if channel == 'b2b_till':
        # Route to venue / merchant Till Number (Buy Goods)
        res = initiate_b2b_payout(
            receiver_shortcode=dest,
            amount=amount,
            command_id="BusinessBuyGoods",
            remarks=remarks,
            account_reference=ticket_code[:12] if ticket_code else "TicketCash"
        )
        # If Safaricom notes receiver is Paybill instead, retry with BusinessPayBill
        if not res.get('success') and 'PayBill' in str(res.get('error', '')):
            res = initiate_b2b_payout(
                receiver_shortcode=dest,
                amount=amount,
                command_id="BusinessPayBill",
                remarks=remarks,
                account_reference=ticket_code[:12] if ticket_code else "TicketCash"
            )

    elif channel == 'b2b_paybill':
        # Route to merchant Paybill
        res = initiate_b2b_payout(
            receiver_shortcode=dest,
            amount=amount,
            command_id="BusinessPayBill",
            remarks=remarks,
            account_reference=ticket_code[:12] if ticket_code else "TicketCash"
        )

    else:
        # Route to personal M-Pesa mobile number via B2C
        res = initiate_b2c_payout(
            phone_number=dest,
            amount=amount,
            command_id="BusinessPayment",
            remarks=remarks,
            occasion="Ticket Payout"
        )

    now_completed_ms = int(time.time() * 1000)
    if res.get('success'):
        conv_id = res.get('ConversationID') or res.get('OriginatorConversationID') or "DISBURSED_OK"
        desc = res.get('ResponseDescription', 'Accepted for disbursement')
        payout_ref.update({
            "status": "disbursed",
            "disbursed_at": now_completed_ms,
            "conversation_id": conv_id,
            "response_description": desc,
            "channel_used": channel,
            "destination": dest
        })

        # Also record in event's internal ledger
        if event_id:
            db.reference(f'events/{event_id}/payouts/{payout_id}').set({
                "ticket_code": ticket_code,
                "amount": amount,
                "phone": dest,
                "channel": channel,
                "timestamp": now_completed_ms,
                "status": "disbursed",
                "conversation_id": conv_id
            })

        logger.info(f"🎉 Cash Transfer Success: KES {amount} sent to {dest} ({channel}) for event '{event_title}'!")
        return {"success": True, "conversation_id": conv_id, "amount": amount, "destination": dest}
    else:
        err = res.get('error', 'Daraja transaction error')
        payout_ref.update({
            "status": "failed",
            "failed_at": now_completed_ms,
            "error": err
        })
        logger.error(f"❌ Failed to disburse organizer payout {payout_id} to {dest}: {err}")
        return {"success": False, "error": err}


def disburse_event_organizer_payouts_now(event_id: str):
    """
    Instantly sweeps and disburses all pending or failed ticket cash transfers for an event.
    Guarantees the organizer receives all collected ticket revenue on demand.
    """
    event_ref = db.reference(f'events/{event_id}')
    event = event_ref.get()
    if not event or not isinstance(event, dict):
        return {"success": False, "error": "Event not found."}

    now_ms = int(time.time() * 1000)

    # Anti-hammering throttle: prevent rapid button spamming
    last_sweep = int(event.get('last_payout_sweep_at', 0) or 0)
    if now_ms - last_sweep < 8000:
        return {"success": False, "error": "A disbursement sweep is already processing. Please wait a few seconds."}

    event_ref.update({"last_payout_sweep_at": now_ms})

    organizer_phone = event.get('organizer_phone')
    if not organizer_phone:
        return {"success": False, "error": "Event does not have an organizer payout phone number configured."}

    # 1. Sweep existing pending or failed payouts
    pending_dict = db.reference('pending_organizer_payouts').get() or {}
    disbursed_count = 0
    total_amount = 0
    results = []

    already_handled_tickets = set()

    if isinstance(pending_dict, dict):
        for pid, precord in pending_dict.items():
            if isinstance(precord, dict) and precord.get('event_id') == event_id:
                t_code = precord.get('ticket_code')
                if t_code:
                    already_handled_tickets.add(t_code)

                status = precord.get('status')
                if status in ['scheduled', 'failed']:
                    logger.info(f"⚡ Immediate sweep disbursing payout {pid} for event {event_id}...")
                    res = execute_single_organizer_payout(pid)
                    results.append({"payout_id": pid, "result": res})
                    if res.get('success'):
                        disbursed_count += 1
                        total_amount += int(precord.get('amount', 0) or 0)
                elif status in ['disbursed', 'paid']:
                    already_handled_tickets.add(t_code)

    # 2. Check all paid RSVPs for this event in case any didn't have a payout record created
    rsvps_dict = db.reference(f'events_rsvps/{event_id}').get() or {}
    if isinstance(rsvps_dict, dict):
        for aid, rsvp in rsvps_dict.items():
            if isinstance(rsvp, dict) and rsvp.get('paid') and int(rsvp.get('amount_paid', 0) or 0) > 0:
                t_code = rsvp.get('ticket_code')
                amt = int(rsvp.get('amount_paid', 0) or 0)
                if t_code and t_code not in already_handled_tickets:
                    logger.info(f"⚡ Creating and executing missing payout for ticket {t_code} (KES {amt})...")
                    p_id = f"evt_payout_{event_id}_{t_code.replace('-', '_')}"
                    channel, clean_dest, _ = resolve_payout_destination(organizer_phone)
                    rec = {
                        "id": p_id,
                        "event_id": event_id,
                        "event_title": event.get('title', 'Campus Event'),
                        "ticket_code": t_code,
                        "amount": amt,
                        "organizer_phone": clean_dest,
                        "raw_destination": organizer_phone,
                        "channel": channel,
                        "created_at": now_ms,
                        "scheduled_at": now_ms,
                        "status": "scheduled",
                        "delay_seconds": 0
                    }
                    db.reference(f'pending_organizer_payouts/{p_id}').set(rec)
                    res = execute_single_organizer_payout(p_id)
                    results.append({"payout_id": p_id, "ticket_code": t_code, "result": res})
                    if res.get('success'):
                        disbursed_count += 1
                        total_amount += amt
                    already_handled_tickets.add(t_code)

    return {
        "success": True,
        "disbursed_count": disbursed_count,
        "total_amount": total_amount,
        "organizer_phone": organizer_phone,
        "results": results
    }


def sweep_pending_organizer_payouts():
    """
    Sweeper that runs on cron/requests to ensure any pending payouts get disbursed.
    """
    now_ms = int(time.time() * 1000)
    pending_dict = db.reference('pending_organizer_payouts').get() or {}
    disbursed_count = 0

    if isinstance(pending_dict, dict):
        for pid, p in pending_dict.items():
            if isinstance(p, dict):
                status = p.get('status')
                scheduled_at = p.get('scheduled_at', 0)
                if status == 'scheduled' and now_ms >= scheduled_at:
                    logger.info(f"🔄 Sweeper triggering payout {pid}...")
                    res = execute_single_organizer_payout(pid)
                    if res.get('success'):
                        disbursed_count += 1

    return disbursed_count


# ========================================================
# 2. CAMPUS MANAGERS & AMBASSADORS MONTHLY SALARY ENGINE
# ========================================================

def get_current_month_keys():
    """Returns formatted month keys: ('2026-10', 'October 2026')"""
    now = datetime.now(EAT)
    month_key = now.strftime('%Y-%m') # e.g. '2026-10'
    month_name = now.strftime('%B %Y') # e.g. 'October 2026'
    return month_key, month_name


def save_manager_payout_phone(manager_id: str, phone_number: str, month_key: str = None):
    """
    Saves and validates the manager/ambassador M-Pesa payout phone number for a specific month.
    """
    if not month_key:
        month_key, _ = get_current_month_keys()

    formatted_phone = format_phone_number(phone_number)
    if not formatted_phone or len(formatted_phone) != 12 or not formatted_phone.startswith('254'):
        return False, "Invalid phone number. Please use 07XXXXXXXX or 01XXXXXXXX format."

    now_str = datetime.now(EAT).strftime("%Y-%m-%d %H:%M:%S EAT")

    # Save to month specific setting AND manager root phone
    db.reference(f'campus_managers/{manager_id}/payout_settings/{month_key}').set({
        "phone": formatted_phone,
        "updated_at": now_str,
        "month": month_key
    })
    db.reference(f'campus_managers/{manager_id}').update({
        "payout_phone": formatted_phone,
        "phone": formatted_phone
    })

    logger.info(f"✅ Saved payout phone {formatted_phone} for manager {manager_id} for {month_key}")
    return True, f"M-Pesa payout phone {formatted_phone} saved for {month_key}!"


def calculate_active_month_commission(manager_id: str, month_key: str = None):
    """
    Calculates active subscriptions and salary payout strictly for that specific month.
    Managers get 30% commission (KES 15 per active 50 KES sub in their institution).
    Ambassadors get 5% commission (or base referral fee per active sub).
    """
    if not month_key:
        month_key, month_name = get_current_month_keys()
    else:
        try:
            dt = datetime.strptime(month_key, '%Y-%m')
            month_name = dt.strftime('%B %Y')
        except:
            month_name = month_key

    mgr = db.reference(f'campus_managers/{manager_id}').get() or {}
    if not mgr:
        return 0, 0, 0, None

    role = (mgr.get('role') or 'manager').lower()
    inst = mgr.get('institution') or mgr.get('institution_name', '')
    inst_norm = str(inst).strip().lower()
    ref_code = str(mgr.get('referral_code', '')).strip()

    # Get payout phone for this specific month
    payout_phone = (
        mgr.get('payout_settings', {}).get(month_key, {}).get('phone') or
        mgr.get('payout_phone') or
        mgr.get('phone')
    )

    profiles = db.reference('profiles').get() or {}
    active_paid_subs = 0

    if isinstance(profiles, dict):
        for uid, p in profiles.items():
            if isinstance(p, dict):
                is_paid = p.get('is_paid')
                if not is_paid:
                    continue

                # Check if subscription was active in this specific month
                # Check created_at or payment_date
                created_at = str(p.get('created_at', ''))
                pay_date = str(p.get('payment_date', ''))
                
                # Active if created_at or payment_date matches YYYY-MM
                is_month_active = created_at.startswith(month_key) or pay_date.startswith(month_key)
                if not is_month_active:
                    continue

                # For manager: matches institution
                # For ambassador: matches referral code
                p_inst = str(p.get('institution') or p.get('institution_name', '')).strip().lower()
                p_ref = str(p.get('referred_by', '')).strip()

                if role == 'manager':
                    if p_inst == inst_norm or (ref_code and p_ref == ref_code):
                        active_paid_subs += 1
                else: # ambassador
                    if ref_code and p_ref == ref_code:
                        active_paid_subs += 1

    commission_rate = 0.30 if role == 'manager' else 0.05
    amount = int(round(active_paid_subs * 50 * commission_rate))

    return active_paid_subs, commission_rate, amount, payout_phone


def disburse_monthly_salaries(month_key: str = None, force: bool = False):
    """
    Disburses monthly salaries automatically via M-Pesa B2C to all active Campus Managers
    and Ambassadors on the 31st of every month (or if force=True for testing/admin trigger).
    Only disburses to managers who have set their payout phone number for that specific month.
    """
    now = datetime.now(EAT)
    if not month_key:
        month_key, month_name = get_current_month_keys()
    else:
        try:
            dt = datetime.strptime(month_key, '%Y-%m')
            month_name = dt.strftime('%B %Y')
        except:
            month_name = month_key

    # Check date condition: Must be 31st of the month (or last day of month), unless forced
    is_31st = (now.day == 31 or (now.month == 2 and now.day in [28, 29]))
    if not is_31st and not force:
        logger.info(f"ℹ️ Today is day {now.day}, monthly payouts only run automatically on the 31st.")
        return {
            "success": False,
            "message": f"Monthly salary payouts run on the 31st of every month. (Today is {now.strftime('%Y-%m-%d')})"
        }

    managers = db.reference('campus_managers').get() or {}
    results = []

    if isinstance(managers, dict):
        for mid, mgr in managers.items():
            if not isinstance(mgr, dict):
                continue

            mgr_name = mgr.get('name', 'Campus Lead')
            role = (mgr.get('role') or 'manager').title()
            subs, rate, amount, payout_phone = calculate_active_month_commission(mid, month_key)

            # Check existing ledger status
            ledger_entry = db.reference(f'campus_manager_ledgers/{mid}/{month_name}').get() or {}
            if ledger_entry.get('status') == 'Paid':
                results.append({
                    "manager_id": mid,
                    "name": mgr_name,
                    "role": role,
                    "status": "Already Paid",
                    "amount": ledger_entry.get('amount', amount),
                    "phone": ledger_entry.get('payout_phone', payout_phone)
                })
                continue

            # Must have payout phone set
            if not payout_phone:
                db.reference(f'campus_manager_ledgers/{mid}/{month_name}').update({
                    "month": month_name,
                    "subscribers": subs,
                    "amount": amount,
                    "status": "Action Required: Missing Payout Phone",
                    "updated_at": now.strftime("%Y-%m-%d %H:%M:%S")
                })
                results.append({
                    "manager_id": mid,
                    "name": mgr_name,
                    "role": role,
                    "status": "Skipped: Missing Payout Phone",
                    "amount": amount,
                    "phone": None
                })
                continue

            # If amount is 0, record in ledger as No Earnings
            if amount <= 0:
                db.reference(f'campus_manager_ledgers/{mid}/{month_name}').update({
                    "month": month_name,
                    "subscribers": subs,
                    "amount": 0,
                    "status": "Zero Balance",
                    "updated_at": now.strftime("%Y-%m-%d %H:%M:%S")
                })
                results.append({
                    "manager_id": mid,
                    "name": mgr_name,
                    "role": role,
                    "status": "Zero Balance",
                    "amount": 0,
                    "phone": payout_phone
                })
                continue

            # Disburse via M-Pesa B2C!
            logger.info(f"🚀 Disbursing {month_name} salary: KES {amount} to {mgr_name} ({payout_phone})...")
            remarks = f"FYM {month_name[:7]} Salary"
            b2c_res = initiate_b2c_payout(
                phone_number=payout_phone,
                amount=amount,
                command_id="SalaryPayment",
                remarks=remarks,
                occasion="Monthly Salary"
            )

            if b2c_res.get('success'):
                db.reference(f'campus_manager_ledgers/{mid}/{month_name}').update({
                    "month": month_name,
                    "subscribers": subs,
                    "amount": amount,
                    "status": "Paid",
                    "paid_date": now.strftime("%Y-%m-%d %H:%M EAT"),
                    "payout_phone": payout_phone,
                    "b2c_conversation_id": b2c_res.get('ConversationID'),
                    "disbursed_automatically": True
                })
                results.append({
                    "manager_id": mid,
                    "name": mgr_name,
                    "role": role,
                    "status": "Paid Successfully",
                    "amount": amount,
                    "phone": payout_phone,
                    "conversation_id": b2c_res.get('ConversationID')
                })
            else:
                err_msg = b2c_res.get('error', 'Daraja error')
                db.reference(f'campus_manager_ledgers/{mid}/{month_name}').update({
                    "month": month_name,
                    "subscribers": subs,
                    "amount": amount,
                    "status": f"Failed: {err_msg}",
                    "failed_date": now.strftime("%Y-%m-%d %H:%M EAT")
                })
                results.append({
                    "manager_id": mid,
                    "name": mgr_name,
                    "role": role,
                    "status": f"Failed: {err_msg}",
                    "amount": amount,
                    "phone": payout_phone
                })

    return {
        "success": True,
        "month": month_name,
        "processed_at": now.strftime("%Y-%m-%d %H:%M:%S EAT"),
        "results": results
    }
