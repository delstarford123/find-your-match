import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from app.database import db
from app.payments import format_phone_number

logger = logging.getLogger(__name__)

# East Africa Time (UTC+3) for accurate timestamps and midnight resets
EAT = timezone(timedelta(hours=3))

DEFAULT_WEEKLY_SLOTS_LIMIT = 10
DAILY_ENGAGEMENT_TARGET = 10
DAILY_REWARD_KES = 50


def get_current_week_key(dt=None) -> str:
    """Returns ISO year and week key, e.g. '2026-W43'."""
    if dt is None:
        dt = datetime.now(EAT)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def get_week_bounds(dt=None):
    """Returns the Monday start and Sunday end dates for the current week."""
    if dt is None:
        dt = datetime.now(EAT)
    # weekday(): Monday is 0, Sunday is 6
    start = dt - timedelta(days=dt.weekday())
    end = start + timedelta(days=6)
    return start.strftime("%b %d"), end.strftime("%b %d, %Y")


def get_cohort_status(user_id: str = None) -> dict:
    """
    Retrieves the status of the current week's 10-lady reward cohort.
    Includes live slot counts, enrollment status, today's progress, and wallet info.
    """
    now_eat = datetime.now(EAT)
    week_key = get_current_week_key(now_eat)
    today_str = now_eat.strftime("%Y-%m-%d")
    week_start, week_end = get_week_bounds(now_eat)

    cohort_ref = db.reference(f'lady_weekly_cohorts/{week_key}')
    cohort_data = cohort_ref.get() or {}

    slots_limit = int(cohort_data.get('slots_limit', DEFAULT_WEEKLY_SLOTS_LIMIT))
    enrolled_ladies = cohort_data.get('enrolled_ladies', {})
    if not isinstance(enrolled_ladies, dict):
        enrolled_ladies = {}

    enrolled_count = len(enrolled_ladies)
    is_full = enrolled_count >= slots_limit
    slots_remaining = max(0, slots_limit - enrolled_count)

    is_enrolled = False
    if user_id and str(user_id) in enrolled_ladies:
        is_enrolled = True

    # User-specific progress & wallet
    today_count = 0
    goal_reached = False
    wallet_balance = 0
    phone_number = ""
    lifetime_earned = 0

    if user_id:
        # Today's engagement progress
        today_data = db.reference(f'lady_daily_engagements/{user_id}/{today_str}').get() or {}
        if isinstance(today_data, dict):
            today_count = int(today_data.get('count', 0))
            goal_reached = bool(today_data.get('goal_reached', False))

        # Wallet data
        wallet_data = db.reference(f'lady_wallets/{user_id}').get() or {}
        if isinstance(wallet_data, dict):
            wallet_balance = int(wallet_data.get('unpaid_balance', 0))
            phone_number = str(wallet_data.get('phone_number', ''))
            lifetime_earned = int(wallet_data.get('lifetime_earned', 0))

        if not phone_number:
            profile = db.reference(f'profiles/{user_id}').get() or {}
            phone_number = profile.get('phone', '')

    return {
        "success": True,
        "week_key": week_key,
        "week_label": f"{week_start} – {week_end}",
        "slots_limit": slots_limit,
        "enrolled_count": enrolled_count,
        "slots_remaining": slots_remaining,
        "is_full": is_full,
        "is_enrolled": is_enrolled,
        "daily_target": DAILY_ENGAGEMENT_TARGET,
        "reward_per_day": DAILY_REWARD_KES,
        "today_progress": {
            "count": today_count,
            "target": DAILY_ENGAGEMENT_TARGET,
            "goal_reached": goal_reached,
            "remaining": max(0, DAILY_ENGAGEMENT_TARGET - today_count)
        },
        "wallet": {
            "unpaid_balance": wallet_balance,
            "lifetime_earned": lifetime_earned,
            "phone_number": phone_number
        }
    }


def join_weekly_cohort(user_id: str, phone: str = None) -> dict:
    """
    Enrolls a verified female student into this week's 10-lady reward squad.
    Enforces the strict limit of 10 ladies per week.
    """
    if not user_id:
        return {"success": False, "error": "Authentication required."}

    # 1. Verify profile & gender
    profile = db.reference(f'profiles/{user_id}').get() or {}
    if not profile:
        return {"success": False, "error": "Profile not found."}

    gender = str(profile.get('gender', '')).strip().lower()
    if gender not in ('female', 'f'):
        return {
            "success": False,
            "error": "The Chat-to-Earn program is exclusively available for verified ladies."
        }

    now_eat = datetime.now(EAT)
    week_key = get_current_week_key(now_eat)
    cohort_ref = db.reference(f'lady_weekly_cohorts/{week_key}')

    # 2. Check if already enrolled or if train is full
    cohort_data = cohort_ref.get() or {}
    slots_limit = int(cohort_data.get('slots_limit', DEFAULT_WEEKLY_SLOTS_LIMIT))
    enrolled_ladies = cohort_data.get('enrolled_ladies', {})
    if not isinstance(enrolled_ladies, dict):
        enrolled_ladies = {}

    if str(user_id) in enrolled_ladies:
        return {
            "success": True,
            "already_enrolled": True,
            "message": "You are already aboard this week's train! Keep chatting to earn your daily rewards.",
            "is_enrolled": True
        }

    if len(enrolled_ladies) >= slots_limit:
        return {
            "success": False,
            "is_full": True,
            "error": f"The train is full for this week! All {slots_limit} spots have been claimed. Try again next Monday at 00:00 EAT!"
        }

    # Clean and resolve M-Pesa phone number
    dest_phone = phone or profile.get('phone') or ''
    clean_phone = format_phone_number(dest_phone) if dest_phone else ''

    lady_record = {
        "user_id": user_id,
        "name": profile.get('name', 'Student'),
        "phone": clean_phone,
        "enrolled_at": now_eat.isoformat()
    }

    # Enroll user
    cohort_ref.child(f'enrolled_ladies/{user_id}').set(lady_record)
    new_count = len(enrolled_ladies) + 1
    cohort_ref.update({
        "enrolled_count": new_count,
        "is_full": (new_count >= slots_limit),
        "last_enrolled_at": now_eat.isoformat(),
        "slots_limit": slots_limit
    })

    # Initialize/update wallet
    wallet_ref = db.reference(f'lady_wallets/{user_id}')
    existing_wallet = wallet_ref.get() or {}
    wallet_updates = {
        "phone_number": clean_phone or existing_wallet.get('phone_number', ''),
        "status": "active",
        "last_week_active": week_key,
        "updated_at": now_eat.isoformat()
    }
    if 'unpaid_balance' not in existing_wallet:
        wallet_updates['unpaid_balance'] = 0
    if 'lifetime_earned' not in existing_wallet:
        wallet_updates['lifetime_earned'] = 0
    wallet_ref.update(wallet_updates)

    logger.info(f"🚂 Lady {user_id} enrolled in cohort {week_key} ({new_count}/{slots_limit})")

    return {
        "success": True,
        "is_enrolled": True,
        "message": f"Congratulations! You've secured spot #{new_count} on this week's train. Reply to 10 men today to unlock KES {DAILY_REWARD_KES}!"
    }


def record_engagement_on_message(female_user_id: str, male_user_id: str) -> dict:
    """
    Called whenever a message is sent in /api/chat/send.
    If the sender is an enrolled female in this week's cohort and the recipient is male,
    records distinct engagement for today. Unlocks 50 KES when 10 distinct men are reached.
    """
    if not female_user_id or not male_user_id or female_user_id == male_user_id:
        return {"recorded": False}

    if str(male_user_id).upper() in ('AI_COMPANION', 'SYSTEM_AI'):
        return {"recorded": False}

    now_eat = datetime.now(EAT)
    week_key = get_current_week_key(now_eat)

    # 1. Check if female is enrolled in current week's cohort
    is_enrolled = db.reference(f'lady_weekly_cohorts/{week_key}/enrolled_ladies/{female_user_id}').get()
    if not is_enrolled:
        return {"recorded": False, "reason": "not_enrolled"}

    # 2. Check recipient gender (must be male)
    recipient_profile = db.reference(f'profiles/{male_user_id}').get() or {}
    recipient_gender = str(recipient_profile.get('gender', '')).strip().lower()
    if recipient_gender not in ('male', 'm'):
        return {"recorded": False, "reason": "recipient_not_male"}

    today_str = now_eat.strftime("%Y-%m-%d")
    day_ref = db.reference(f'lady_daily_engagements/{female_user_id}/{today_str}')
    day_data = day_ref.get() or {}

    engaged_men = day_data.get('engaged_men', {})
    if not isinstance(engaged_men, dict):
        engaged_men = {}

    # Already counted this male user today
    if str(male_user_id) in engaged_men:
        return {
            "recorded": False,
            "already_engaged": True,
            "count": len(engaged_men),
            "goal_reached": bool(day_data.get('goal_reached', False))
        }

    # Add male user to today's engaged set
    engaged_men[str(male_user_id)] = now_eat.isoformat()
    count = len(engaged_men)

    reward_credited = bool(day_data.get('reward_credited', False))
    goal_reached = (count >= DAILY_ENGAGEMENT_TARGET)
    newly_unlocked_reward = False

    day_payload = {
        f"engaged_men/{male_user_id}": now_eat.isoformat(),
        "count": count,
        "goal_reached": goal_reached,
        "last_engagement_at": now_eat.isoformat()
    }

    # Check if this message triggers the 10-men reward milestone!
    if goal_reached and not reward_credited:
        day_payload["reward_credited"] = True
        day_payload["reward_amount"] = DAILY_REWARD_KES
        day_payload["completed_at"] = now_eat.isoformat()
        newly_unlocked_reward = True

        # Atomically credit wallet
        wallet_ref = db.reference(f'lady_wallets/{female_user_id}')
        wallet_data = wallet_ref.get() or {}
        current_balance = int(wallet_data.get('unpaid_balance', 0))
        new_balance = current_balance + DAILY_REWARD_KES

        completed_days = int(wallet_data.get('total_days_completed', 0)) + 1

        wallet_ref.update({
            "unpaid_balance": new_balance,
            "total_days_completed": completed_days,
            "last_completed_date": today_str,
            "updated_at": now_eat.isoformat()
        })

        # Send in-app notification
        try:
            db.reference(f'notifications/{female_user_id}').push({
                "title": "🎉 KES 50 Daily Reward Unlocked!",
                "message": f"Amazing work! You engaged with 10 men today. KES {DAILY_REWARD_KES} has been added to your weekly M-Pesa payout wallet (Total: KES {new_balance}).",
                "type": "daily_reward",
                "timestamp": now_eat.isoformat(),
                "status": "unread"
            })
        except Exception as e:
            logger.error(f"Error sending reward notification: {e}")

        logger.info(f"💰 Lady {female_user_id} completed 10 men goal! +{DAILY_REWARD_KES} KES (New Balance: {new_balance})")

    day_ref.update(day_payload)

    return {
        "recorded": True,
        "count": count,
        "target": DAILY_ENGAGEMENT_TARGET,
        "remaining": max(0, DAILY_ENGAGEMENT_TARGET - count),
        "goal_reached": goal_reached,
        "reward_unlocked": newly_unlocked_reward,
        "reward_amount": DAILY_REWARD_KES if newly_unlocked_reward else 0
    }


def save_lady_wallet_phone(user_id: str, raw_phone: str) -> dict:
    """Updates the M-Pesa payout destination phone number for a lady's wallet."""
    if not user_id or not raw_phone:
        return {"success": False, "error": "User ID and phone number required."}

    clean_phone = format_phone_number(raw_phone)
    if not clean_phone or len(clean_phone) != 12 or not clean_phone.startswith("254"):
        return {"success": False, "error": "Invalid Kenyan phone number. Use 07XXXXXXXX or 2547XXXXXXXX."}

    db.reference(f'lady_wallets/{user_id}').update({
        "phone_number": clean_phone,
        "updated_at": datetime.now(EAT).isoformat()
    })
    return {"success": True, "phone_number": clean_phone, "message": f"M-Pesa payout line updated to {clean_phone}."}


def get_ladies_campaign_status() -> dict:
    """Returns the current state and history of the Ladies Chat-to-Earn campaign launch."""
    record = db.reference('system_settings/ladies_campaign_launch').get() or {}
    if not isinstance(record, dict):
        record = {}
    return {
        "is_launched": bool(record.get('is_launched', False)),
        "status": record.get('status', 'idle'),  # 'idle', 'in_progress', 'completed'
        "last_launched_at": record.get('last_launched_at', None),
        "last_launched_by": record.get('last_launched_by', 'Admin'),
        "total_ladies_targeted": int(record.get('total_ladies_targeted', 0)),
        "emails_sent": int(record.get('emails_sent', 0)),
        "notifications_sent": int(record.get('notifications_sent', 0)),
        "errors_count": int(record.get('errors_count', 0)),
        "finished_at": record.get('finished_at', None)
    }


def dispatch_ladies_launch_campaign(admin_name: str = "Super Admin", push_fn=None) -> dict:
    """
    Launches the Ladies Chat-to-Earn & NGL activity by dispatching:
    1. Rich HTML onboarding email with CTA to jump in
    2. Realtime in-app notification with direct /matches link
    3. Mobile/Desktop Web Push and FCM notification
    to all registered female users in the system.
    
    Executes in a background thread to prevent request timeouts.
    """
    now_eat = datetime.now(EAT)
    campaign_ref = db.reference('system_settings/ladies_campaign_launch')
    
    current_status = campaign_ref.get() or {}
    if isinstance(current_status, dict) and current_status.get('status') == 'in_progress':
        return {
            "success": False,
            "error": "A campaign broadcast is currently in progress. Please wait for it to complete."
        }

    # Fetch all registered user profiles
    all_profiles = db.reference('profiles').get() or {}
    if not isinstance(all_profiles, dict):
        all_profiles = {}

    target_ladies = []
    for uid, profile in all_profiles.items():
        if not isinstance(profile, dict):
            continue
        gender = str(profile.get('gender', '')).strip().lower()
        if gender in ['female', 'woman', 'girl', 'f']:
            # Lady found
            target_ladies.append({
                "uid": uid,
                "name": profile.get('name') or profile.get('full_name') or 'Comrade',
                "email": profile.get('email', '').strip(),
                "phone": profile.get('phone', '').strip()
            })

    total_count = len(target_ladies)
    if total_count == 0:
        return {
            "success": False,
            "error": "No female profiles found in database to broadcast to."
        }

    # Mark campaign launch started
    launch_meta = {
        "is_launched": True,
        "status": "in_progress",
        "last_launched_at": now_eat.strftime("%Y-%m-%d %H:%M:%S EAT"),
        "last_launched_by": admin_name,
        "total_ladies_targeted": total_count,
        "emails_sent": 0,
        "notifications_sent": 0,
        "errors_count": 0,
        "finished_at": None
    }
    campaign_ref.update(launch_meta)

    # Log to admin audit logs
    try:
        db.reference('admin_audit_logs').push({
            'action': f"Launched Ladies Chat-to-Earn & NGL Campaign to {total_count} ladies",
            'timestamp': now_eat.strftime("%Y-%m-%d %H:%M:%S EAT"),
            'admin': admin_name
        })
    except Exception as e:
        logger.warning(f"Could not record audit log: {e}")

    def _broadcast_worker():
        from app.email_service import send_ladies_chat_earn_launch_email
        emails_sent = 0
        notifs_sent = 0
        errors = 0

        for lady in target_ladies:
            uid = lady['uid']
            name = lady['name']
            email = lady['email']

            # 1. Dispatch In-App Notification
            try:
                db.reference(f'notifications/{uid}').push({
                    "title": "🚂 Chat-to-Earn Squad Launched (50 KES Daily)!",
                    "message": "We've officially launched the Chat-to-Earn Train! Reply to 10 men daily to earn 50 KES to your M-Pesa every Sunday. Only 10 spots open this week — claim yours now!",
                    "type": "ladies_campaign_launch",
                    "click_url": "/matches",
                    "timestamp": datetime.now(EAT).isoformat(),
                    "status": "unread"
                })
                notifs_sent += 1
            except Exception as ne:
                logger.error(f"Failed to push in-app notification to {uid}: {ne}")
                errors += 1

            # 2. Dispatch Web Push / FCM
            if push_fn:
                try:
                    push_fn(
                        receiver_id=uid,
                        title="🚂 Chat-to-Earn Squad Launched (50 KES Daily)!",
                        body="Earn KES 50 daily to M-Pesa + get your anonymous WhatsApp link! Only 10 spots open this week.",
                        click_url="/matches",
                        tag="ladies_launch"
                    )
                except Exception as pe:
                    logger.debug(f"Push error for {uid}: {pe}")

            # 3. Dispatch Email
            if email and "@" in email:
                try:
                    ok = send_ladies_chat_earn_launch_email(
                        recipient_email=email,
                        recipient_name=name
                    )
                    if ok:
                        emails_sent += 1
                    else:
                        errors += 1
                except Exception as ee:
                    logger.error(f"Failed sending launch email to {email}: {ee}")
                    errors += 1

            # Small throttle to avoid hitting SMTP rate limits too fast
            time.sleep(0.1)

        # Mark campaign completed
        finish_eat = datetime.now(EAT)
        campaign_ref.update({
            "status": "completed",
            "emails_sent": emails_sent,
            "notifications_sent": notifs_sent,
            "errors_count": errors,
            "finished_at": finish_eat.strftime("%Y-%m-%d %H:%M:%S EAT")
        })
        logger.info(f"✅ Ladies launch campaign finished. Targeted: {total_count}, Emails: {emails_sent}, Notifs: {notifs_sent}, Errors: {errors}")

    # Fire background worker
    worker_thread = threading.Thread(target=_broadcast_worker, daemon=True)
    worker_thread.start()

    return {
        "success": True,
        "message": f"Activity launch initiated! Dispatching launch email and notifications to {total_count} ladies in the background.",
        "target_count": total_count,
        "launched_at": launch_meta["last_launched_at"]
    }
