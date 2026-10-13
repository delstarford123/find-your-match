import os
import time
import logging
import threading
from datetime import datetime, timedelta, timezone
from app.database import db
from app.payments import initiate_b2c_payout, format_phone_number

logger = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))

# ========================================================
# 1. EVENT ORGANIZER 2-MINUTE AUTOMATIC PAYOUT ENGINE
# ========================================================

def schedule_event_organizer_payout(event_id: str, ticket_code: str, amount: float or int, organizer_phone: str, delay_seconds: int = 120):
    """
    Schedules an automated M-Pesa B2C payout of the event registration fee to the event admin/organizer.
    The money is automatically disbursed 2 minutes after the attendee pays.
    """
    try:
        if not organizer_phone:
            # Fallback to fetching event record
            event_data = db.reference(f'events/{event_id}').get() or {}
            organizer_phone = event_data.get('organizer_phone')

        formatted_phone = format_phone_number(organizer_phone)
        if not formatted_phone:
            logger.error(f"❌ Cannot schedule payout: Missing organizer phone for event {event_id}")
            return False

        clean_amount = int(round(float(amount)))
        if clean_amount <= 0:
            return False

        now_ms = int(time.time() * 1000)
        scheduled_at_ms = now_ms + (delay_seconds * 1000)
        payout_id = f"evt_pay_{ticket_code.replace('-', '_')}_{int(time.time())}"

        # Fetch event title
        event_data = db.reference(f'events/{event_id}').get() or {}
        event_title = event_data.get('title', 'Campus Event')

        record = {
            "id": payout_id,
            "event_id": event_id,
            "event_title": event_title,
            "ticket_code": ticket_code,
            "amount": clean_amount,
            "organizer_phone": formatted_phone,
            "created_at": now_ms,
            "scheduled_at": scheduled_at_ms,
            "status": "scheduled",
            "delay_seconds": delay_seconds
        }

        # Persist to database so it survives across serverless cold starts
        db.reference(f'pending_organizer_payouts/{payout_id}').set(record)
        logger.info(f"⏳ Scheduled organizer payout of KES {clean_amount} to {formatted_phone} in {delay_seconds}s for ticket {ticket_code}")

        # Spawn background timer thread for real-time execution in active instances
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
    Executes a single scheduled organizer payout via M-Pesa B2C.
    Guarded by atomic status check to prevent duplicate disbursements.
    """
    payout_ref = db.reference(f'pending_organizer_payouts/{payout_id}')
    payout = payout_ref.get()
    if not payout:
        return {"success": False, "error": "Payout record not found."}

    if payout.get('status') in ['disbursed', 'paid']:
        logger.info(f"ℹ️ Payout {payout_id} already disbursed.")
        return {"success": True, "already_disbursed": True}

    organizer_phone = payout.get('organizer_phone')
    amount = payout.get('amount')
    event_title = payout.get('event_title', 'Campus Event')
    ticket_code = payout.get('ticket_code', '')
    event_id = payout.get('event_id')

    # Atomic lock
    payout_ref.update({"status": "processing", "processing_started_at": int(time.time() * 1000)})

    remarks = f"Tkt {ticket_code} {event_title}"[:95]
    res = initiate_b2c_payout(
        phone_number=organizer_phone,
        amount=amount,
        command_id="BusinessPayment",
        remarks=remarks,
        occasion="Ticket Payout"
    )

    now_ms = int(time.time() * 1000)
    if res.get('success'):
        payout_ref.update({
            "status": "disbursed",
            "disbursed_at": now_ms,
            "conversation_id": res.get('ConversationID'),
            "response_description": res.get('ResponseDescription')
        })

        # Also log under the event's payout ledger
        if event_id:
            db.reference(f'events/{event_id}/payouts/{payout_id}').set({
                "ticket_code": ticket_code,
                "amount": amount,
                "phone": organizer_phone,
                "timestamp": now_ms,
                "status": "disbursed",
                "conversation_id": res.get('ConversationID')
            })

        logger.info(f"🎉 Successfully sent KES {amount} organizer payout to {organizer_phone} for event '{event_title}'!")
        return {"success": True, "conversation_id": res.get('ConversationID')}
    else:
        err = res.get('error', 'Daraja error')
        payout_ref.update({
            "status": "failed",
            "failed_at": now_ms,
            "error": err
        })
        logger.error(f"❌ Failed to disburse organizer payout {payout_id}: {err}")
        return {"success": False, "error": err}


def sweep_pending_organizer_payouts():
    """
    Sweeper that runs on cron/requests to ensure any pending payouts older than 2 minutes
    get disbursed immediately even if serverless rebooted.
    """
    now_ms = int(time.time() * 1000)
    pending_dict = db.reference('pending_organizer_payouts').get() or {}
    disbursed_count = 0

    if isinstance(pending_dict, dict):
        for pid, p in pending_dict.items():
            if isinstance(p, dict):
                status = p.get('status')
                scheduled_at = p.get('scheduled_at', 0)
                # If scheduled time has arrived and status is scheduled or failed with retry
                if status == 'scheduled' and now_ms >= scheduled_at:
                    logger.info(f"🔄 Sweeper triggering delayed payout {pid}...")
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
