#!/usr/bin/env python3
"""
send_free_trial_campaign.py
-------------------------------------------------------------------------------
Find Your Match (findyourmatch.co.ke)
Automated 2-Day Complimentary VIP Diamond Access Campaign.

Grants 48 hours of full, unrestricted Diamond VIP access to all registered users 
who do not currently have an active subscription, and delivers an executive, 
responsive email showcasing all new features with direct jump links:
  1. 1-on-1 Live Voice & Video Calls (/talk)
  2. Campus Group Chats (/groups)
  3. Multi-Peer Group Voice & Video Hangout Rooms (/groups)
  4. Sponsor Meet / Sponsors Room (/sponsors-room)
  5. AI Smart Match Feed & Instant Swiping (/dashboard)

Features:
  - Preserves all active paid subscribers (they are NEVER downgraded or overwritten).
  - Can be run LOCALLY or orchestrated VIA VERCEL SERVER.
  - Multi-path Firebase update grants 2-day access to all 640+ inactive users in < 2 seconds.

Usage:
  # 1. DRY RUN (inspect eligible candidates & stats without touching DB or sending emails):
  python send_free_trial_campaign.py --dry-run

  # 2. ACTIVATE 2-DAY VIP ACCESS IN DATABASE FIRST (Super fast, takes 2 seconds):
  python send_free_trial_campaign.py --apply-only

  # 3. TEST EMAIL DISPATCH (send 1 preview to your personal inbox):
  python send_free_trial_campaign.py --test delstarfordisaiah@gmail.com
  # Or test via live Vercel server:
  python send_free_trial_campaign.py --test delstarfordisaiah@gmail.com --via-server

  # 4. SEND EMAILS VIA VERCEL (Recommended: AWS server dispatches in batches of 20, avoids ISP port blocks):
  python send_free_trial_campaign.py --via-server

  # 5. SEND EMAILS VIA LOCAL SMTP (if local network has SMTP port 465 open):
  python send_free_trial_campaign.py
-------------------------------------------------------------------------------
"""

import os
import sys
import time
import logging
import argparse
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load local environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import initialize_firebase, db, clear_profiles_cache
from email_service import (
    build_free_trial_email_content,
    send_free_trial_announcement_email,
    _send_email,
    SENDER_NAME_DEFAULT
)

# Setup logging
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/free_trial_campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logger = logging.getLogger("free_trial_campaign")
logger.setLevel(logging.INFO)
logger.propagate = False

if logger.hasHandlers():
    logger.handlers.clear()

c_handler = logging.StreamHandler(sys.stdout)
f_handler = logging.FileHandler(log_filename, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
c_handler.setFormatter(formatter)
f_handler.setFormatter(formatter)
logger.addHandler(c_handler)
logger.addHandler(f_handler)

EAT = timezone(timedelta(hours=3))
BASE_URL = os.getenv("BASE_URL", "https://www.findyourmatch.co.ke").rstrip("/")
CRON_SECRET = os.getenv("CRON_SECRET_KEY", "mmust_dating_cron_secret_2026")


def get_eligible_users():
    """
    Fetches all profiles from Firebase Realtime Database and identifies users 
    WITHOUT an active subscription who have a valid email address.
    """
    initialize_firebase()
    all_profiles = db.reference("profiles").get() or {}

    now = datetime.now(EAT)
    candidates = []
    active_subscribers = []
    no_email_count = 0

    for uid, profile in all_profiles.items():
        if not isinstance(profile, dict):
            continue

        email = str(profile.get("email", "")).strip()
        if not email or "@" not in email:
            no_email_count += 1
            continue

        # Check if user already has an active paid subscription
        is_paid = profile.get("is_paid", False)
        expiry_str = profile.get("subscription_expiry")
        has_active_sub = False

        if is_paid and expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(str(expiry_str).replace("Z", "+00:00"))
                if expiry_dt.tzinfo is None:
                    expiry_dt = expiry_dt.replace(tzinfo=EAT)
                if now < expiry_dt:
                    has_active_sub = True
            except Exception:
                pass

        if has_active_sub:
            active_subscribers.append(uid)
            continue

        name = str(profile.get("name", "Student")).strip()
        gender = str(profile.get("gender", "")).strip().lower()
        phone = str(profile.get("phone", "N/A")).strip()

        candidates.append({
            "uid": uid,
            "name": name,
            "email": email,
            "gender": gender,
            "phone": phone,
            "current_expiry": expiry_str or "None"
        })

    logger.info("Total profiles scanned : %d", len(all_profiles))
    logger.info("Active paid subscribers : %d (Protected from being touched)", len(active_subscribers))
    logger.info("Profiles without email  : %d (Skipped)", no_email_count)
    logger.info("Eligible inactive users : %d (Qualified for 2-Day Free VIP Access)", len(candidates))

    return candidates


def apply_fast_database_upgrade(candidates, expiry_dt: datetime):
    """
    Performs high-speed multi-path update in Firebase Realtime Database.
    Upgrades all inactive candidates to Diamond VIP for 48 hours in a single network round-trip.
    """
    initialize_firebase()
    now_eat = datetime.now(EAT)
    expiry_iso = expiry_dt.isoformat()
    now_iso = now_eat.isoformat()
    receipt_id = f"PROMO_2DAY_GIFT_{now_eat.strftime('%Y%m%d')}"

    logger.info("Constructing Firebase multi-path payload for %d users...", len(candidates))
    updates = {}
    for user in candidates:
        uid = user["uid"]
        updates[f"{uid}/is_paid"] = True
        updates[f"{uid}/subscription_expiry"] = expiry_iso
        updates[f"{uid}/subscription_package"] = "diamond"
        updates[f"{uid}/sponsor_room_access_until"] = expiry_iso
        updates[f"{uid}/free_trial_granted_at"] = now_iso
        updates[f"{uid}/free_trial_email_sent"] = False
        updates[f"{uid}/last_payment_receipt"] = receipt_id

    try:
        db.reference("profiles").update(updates)
        clear_profiles_cache()
        logger.info("✅ SUCCESS: Successfully granted 2-Day Diamond VIP Access to %d users in Firebase!", len(candidates))
        return True
    except Exception as e:
        logger.error(f"❌ Failed to batch update profiles in Firebase: {e}")
        return False


def run_via_vercel_batches(batch_size: int = 20, delay_between_batches: float = 2.0):
    """
    Coordinates email dispatches through the live Vercel server in safe batches.
    Since Vercel runs in AWS US-East, its outbound connection to HostPinnacle port 465 is never blocked.
    """
    endpoint = f"{BASE_URL}/api/admin/campaign/send-free-trial-batch"
    headers = {"X-Cron-Key": CRON_SECRET}

    logger.info("🚀 Initiating Vercel Server Batch Dispatcher...")
    logger.info("Target Endpoint: %s", endpoint)
    logger.info("Batch Size     : %d emails per request", batch_size)

    total_sent = 0
    total_failed = 0
    batch_num = 1

    while True:
        logger.info(f"--- [Batch #{batch_num}] Calling Vercel to dispatch next {batch_size} emails... ---")
        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                params={"batch_size": batch_size},
                timeout=45
            )
            if resp.status_code != 200:
                logger.error(f"Vercel returned HTTP {resp.status_code}: {resp.text}")
                break

            data = resp.json()
            sent = data.get("sent", 0)
            failed = data.get("failed", 0)
            remaining = data.get("remaining_pending", 0)
            has_more = data.get("has_more", False)

            total_sent += sent
            total_failed += failed

            logger.info(f"  -> Batch #{batch_num} Result: Sent={sent}, Failed={failed}, Remaining Pending={remaining}")

            if not has_more or data.get("batch_processed", 0) == 0:
                logger.info("🎉 All eligible users have received their free trial email!")
                break

            batch_num += 1
            time.sleep(delay_between_batches)

        except Exception as e:
            logger.error(f"Error calling Vercel batch endpoint: {e}")
            break

    logger.info("=" * 70)
    logger.info("  VERCEL CAMPAIGN DISPATCH SUMMARY")
    logger.info("  Total Batches Executed : %d", batch_num)
    logger.info("  Total Delivered        : %d", total_sent)
    logger.info("  Total Failed           : %d", total_failed)
    logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Grant 2-Day Free Diamond VIP Access and send announcement email.")
    parser.add_argument("--dry-run", action="store_true", help="Preview target list without touching DB or sending emails.")
    parser.add_argument("--test", type=str, help="Send a single preview email to your personal address to test layout.")
    parser.add_argument("--apply-only", action="store_true", help="Only activate the 2-day VIP access in Firebase (no emails).")
    parser.add_argument("--via-server", action="store_true", help="Send emails through Vercel server in safe batches (bypasses ISP blocks).")
    parser.add_argument("--email-only", action="store_true", help="Only dispatch emails without modifying Firebase expiry.")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of users to process.")
    parser.add_argument("--delay", type=float, default=1.3, help="Delay in seconds between local SMTP sends (default: 1.3s).")

    args = parser.parse_args()

    now = datetime.now(EAT)
    two_days_later = now + timedelta(days=2)
    expiry_display = two_days_later.strftime("%A, %B %d, %Y at %I:%M %p EAT")

    logger.info("=" * 70)
    logger.info("   FIND YOUR MATCH -- 48-HOUR COMPLIMENTARY VIP CAMPAIGN")
    logger.info("   Target: Inactive / Unpaid Users | Domain: %s", BASE_URL)
    logger.info("   Access Expiry Calculated: %s", expiry_display)
    logger.info("=" * 70)

    # 1. TEST MODE
    if args.test:
        test_email = args.test.strip()
        logger.info("⚡ TEST MODE ACTIVATED: Sending preview email to %s", test_email)

        if args.via_server:
            endpoint = f"{BASE_URL}/api/admin/campaign/test-email"
            logger.info("Dispatching test email via Vercel server: %s", endpoint)
            try:
                res = requests.post(endpoint, headers={"X-Cron-Key": CRON_SECRET}, params={"email": test_email}, timeout=25)
                logger.info("Vercel Response: %s", res.text)
            except Exception as e:
                logger.error("Failed to test via server: %e", e)
        else:
            success = send_free_trial_announcement_email(test_email, "Delstaford (Admin Test)", expiry_display)
            if success:
                logger.info("✅ Test email delivered successfully to %s!", test_email)
            else:
                logger.error("❌ Failed to send locally. (Tip: Try with --via-server to send from Vercel's AWS environment)")
        return

    # 2. FETCH CANDIDATES
    candidates = get_eligible_users()
    total_eligible = len(candidates)

    if not candidates:
        logger.warning("No eligible users found.")
        return

    if args.limit and args.limit < total_eligible:
        candidates = candidates[:args.limit]
        logger.info("Capped batch to first %d users due to --limit flag.", len(candidates))

    # 3. DRY RUN MODE
    if args.dry_run:
        logger.info("\n--- [DRY RUN PREVIEW: FIRST 20 OF %d CANDIDATES] ---", len(candidates))
        for idx, u in enumerate(candidates[:20], 1):
            logger.info(
                f"[{idx:03d}/{len(candidates):03d}] UID: {u['uid'][:10]}... | {u['name']} <{u['email']}> | Prev Exp: {u['current_expiry']}"
            )
        if len(candidates) > 20:
            logger.info("... and %d more inactive users ready for 2-day VIP access.", len(candidates) - 20)
        logger.info("--- END OF DRY RUN (No database updates or emails dispatched) ---")
        logger.info("To activate VIP access in database: python send_free_trial_campaign.py --apply-only")
        logger.info("To send emails via Vercel:          python send_free_trial_campaign.py --via-server")
        return

    # 4. FAST DATABASE ACTIVATION (--apply-only or before email loop)
    if not args.email_only:
        logger.info("Activating 48-Hour Diamond VIP access for %d users in Firebase...", len(candidates))
        db_ok = apply_fast_database_upgrade(candidates, two_days_later)
        if not db_ok:
            logger.error("Failed to update database. Halting.")
            return

        if args.apply_only:
            logger.info("✅ Access applied to all %d users. Exiting as requested by --apply-only.", len(candidates))
            return

    # 5. DISPATCH EMAILS VIA VERCEL SERVER
    if args.via_server:
        run_via_vercel_batches(batch_size=20)
        return

    # 6. LOCAL SMTP DISPATCH
    logger.info("Dispatching %d emails via local SMTP with %.2fs delay...", len(candidates), args.delay)
    sent_count = 0
    failed_count = 0

    for idx, user in enumerate(candidates, 1):
        email = user["email"]
        name = user["name"]
        logger.info(f"[{idx}/{len(candidates)}] Sending to {name} <{email}>...")

        ok = send_free_trial_announcement_email(email, name, expiry_display)
        if ok:
            sent_count += 1
            logger.info(f"  -> ✅ Delivered to {email}")
        else:
            failed_count += 1
            logger.warning(f"  -> ❌ Failed to deliver to {email}")

        if idx < len(candidates):
            time.sleep(args.delay)

    logger.info("=" * 70)
    logger.info("  LOCAL CAMPAIGN DISPATCH COMPLETE")
    logger.info("  Delivered : %d", sent_count)
    logger.info("  Failed    : %d", failed_count)
    logger.info("  Log file  : %s", log_filename)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
