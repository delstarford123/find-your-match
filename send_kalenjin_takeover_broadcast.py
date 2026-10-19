#!/usr/bin/env python3
"""
send_kalenjin_takeover_broadcast.py
-------------------------------------------------------------------------------
Find Your Match (findyourmatch.co.ke)
Broadcast Campaign: KALENJIN TAKE OVER (MMUST EDITION)
Event Link: https://www.findyourmatch.co.ke/events/evt_7124cc20ce

Dispatches the official event invitation email to all active, registered users 
in the system with scannable tickets, lineup details, and direct checkout links.

Usage:
  # 1. Inspect eligible candidate count and preview recipient list:
  python send_kalenjin_takeover_broadcast.py --dry-run

  # 2. Check current broadcast delivery stats:
  python send_kalenjin_takeover_broadcast.py --stats

  # 3. Send test preview to admin email (via server):
  python send_kalenjin_takeover_broadcast.py --test delstarfordisaiah@gmail.com --via-server

  # 4. DISPATCH TO ALL USERS IN THE SYSTEM (Safe batches of 20 via server):
  python send_kalenjin_takeover_broadcast.py --via-server

  # 5. Dispatch via server with a limit (e.g. first 50 users):
  python send_kalenjin_takeover_broadcast.py --via-server --limit 50
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

from database import initialize_firebase, db
from email_service import (
    build_kalenjin_takeover_email_content,
    send_kalenjin_takeover_email,
    SENDER_NAME_DEFAULT
)

# Setup logging
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/kalenjin_takeover_broadcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logger = logging.getLogger("kalenjin_takeover_mailer")
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
EVENT_ID = "evt_7124cc20ce"
DEFAULT_BASE_URL = os.getenv("BASE_URL", "https://www.findyourmatch.co.ke").rstrip("/")
CRON_SECRET = os.getenv("CRON_SECRET_KEY", "mmust_dating_cron_secret_2026")
ADMIN_KEY = "fym_promo_override_2026"


def get_recipients(event_id: str = EVENT_ID):
    """
    Scans Firebase profiles and identifies users eligible for the event broadcast.
    Skips users who already received the email according to `event_broadcast_logs/{event_id}`.
    """
    initialize_firebase()
    all_profiles = db.reference("profiles").get() or {}
    sent_dict = db.reference(f"event_broadcast_logs/{event_id}").get() or {}
    if not isinstance(sent_dict, dict):
        sent_dict = {}

    candidates = []
    already_sent = []
    skipped_no_email = 0
    skipped_banned = 0

    for uid, profile in all_profiles.items():
        if not isinstance(profile, dict):
            continue

        email = str(profile.get("email", "")).strip()
        if not email or "@" not in email:
            skipped_no_email += 1
            continue

        if profile.get("is_banned") or profile.get("email_opt_out"):
            skipped_banned += 1
            continue

        if uid in sent_dict:
            already_sent.append(uid)
            continue

        name = str(profile.get("name") or profile.get("username") or "Comrade").strip()
        candidates.append({
            "uid": uid,
            "name": name,
            "email": email
        })

    logger.info("Total profiles in database: %d", len(all_profiles))
    logger.info("Already received broadcast : %d", len(already_sent))
    logger.info("Skipped (no valid email)   : %d", skipped_no_email)
    logger.info("Skipped (banned/opted out) : %d", skipped_banned)
    logger.info("Eligible pending broadcast : %d", len(candidates))

    return candidates, len(already_sent)


def run_via_server_batches(base_url: str = DEFAULT_BASE_URL, batch_size: int = 20, delay_between_batches: float = 2.0, limit: int = None):
    """
    Dispatches event emails through the server in safe, rate-limited batches.
    Guarantees no local port 465 timeout and ensures steady, verifiable progress.
    """
    endpoint = f"{base_url}/api/admin/campaign/send-event-broadcast-batch"
    headers = {"X-Cron-Key": CRON_SECRET, "X-Admin-Key": ADMIN_KEY}

    logger.info("🚀 Initiating Server Batch Broadcast...")
    logger.info("Target Endpoint: %s", endpoint)
    logger.info("Event ID       : %s", EVENT_ID)
    logger.info("Batch Size     : %d emails per request", batch_size)
    if limit:
        logger.info("Limit Capped   : First %d users only", limit)

    total_sent = 0
    total_failed = 0
    batch_num = 1

    while True:
        current_request_batch = batch_size
        if limit:
            remaining_limit = limit - total_sent
            if remaining_limit <= 0:
                logger.info("Reached specified limit of %d sent emails. Stopping.", limit)
                break
            current_request_batch = min(batch_size, remaining_limit)

        logger.info(f"--- [Batch #{batch_num}] Requesting server to dispatch next {current_request_batch} emails... ---")
        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                params={
                    "event_id": EVENT_ID,
                    "batch_size": current_request_batch,
                    "admin_key": ADMIN_KEY
                },
                timeout=55
            )

            if resp.status_code != 200:
                logger.error(f"Server returned HTTP {resp.status_code}: {resp.text}")
                break

            data = resp.json()
            sent = data.get("sent", 0)
            failed = data.get("failed", 0)
            remaining = data.get("remaining_pending", 0)
            has_more = data.get("has_more", False)
            processed = data.get("batch_processed", 0)

            total_sent += sent
            total_failed += failed

            logger.info(f"  -> Batch #{batch_num} Result: Sent={sent}, Failed={failed}, Remaining Pending={remaining}")

            if not has_more or processed == 0:
                logger.info("🎉 All eligible users have received the KALENJIN TAKE OVER event email!")
                break

            batch_num += 1
            time.sleep(delay_between_batches)

        except Exception as e:
            logger.error(f"Error calling broadcast endpoint: {e}")
            break

    logger.info("=" * 70)
    logger.info("  EVENT BROADCAST SUMMARY")
    logger.info("  Total Batches Executed : %d", batch_num)
    logger.info("  Total Emails Delivered : %d", total_sent)
    logger.info("  Total Delivery Errors  : %d", total_failed)
    logger.info("=" * 70)


def send_test_preview(test_email: str, via_server: bool = False, base_url: str = DEFAULT_BASE_URL):
    """
    Sends a test email to preview layout and styling.
    """
    logger.info("⚡ TEST PREVIEW: Sending preview to %s", test_email)
    event_url = f"{base_url}/events/{EVENT_ID}"

    if via_server:
        endpoint = f"{base_url}/api/admin/campaign/test-event-email"
        logger.info("Calling server test endpoint: %s", endpoint)
        try:
            res = requests.post(
                endpoint,
                headers={"X-Cron-Key": CRON_SECRET, "X-Admin-Key": ADMIN_KEY},
                params={
                    "email": test_email,
                    "name": "Delstaford (Admin Test)",
                    "event_id": EVENT_ID,
                    "admin_key": ADMIN_KEY
                },
                timeout=35
            )
            logger.info("Server Response: %s", res.text)
            if res.status_code == 200 and res.json().get("delivered"):
                logger.info("✅ Test preview email successfully delivered to %s!", test_email)
                return True
            else:
                logger.error("❌ Test preview failed via server.")
                return False
        except Exception as e:
            logger.error(f"Failed to send test via server: {e}")
            return False
    else:
        ok = send_kalenjin_takeover_email(
            recipient_email=test_email,
            recipient_name="Delstaford (Admin Test)",
            event_url=event_url
        )
        if ok:
            logger.info("✅ Local test preview delivered to %s!", test_email)
        else:
            logger.error("❌ Local send failed (Likely blocked port 465 on local network. Use --via-server).")
        return ok


def main():
    parser = argparse.ArgumentParser(description="KALENJIN TAKE OVER (MMUST EDITION) Broadcast Mailer")
    parser.add_argument("--dry-run", action="store_true", help="Preview recipient candidates without sending.")
    parser.add_argument("--stats", action="store_true", help="Check live broadcast delivery status.")
    parser.add_argument("--test", type=str, help="Send a single test preview email.")
    parser.add_argument("--via-server", action="store_true", help="Dispatch via server in safe batches.")
    parser.add_argument("--server-url", type=str, default=DEFAULT_BASE_URL, help="Custom server base URL.")
    parser.add_argument("--limit", type=int, default=None, help="Cap the number of recipients.")
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size per request (default: 20).")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay in seconds between batches.")
    parser.add_argument("--reset-sent", action="store_true", help="Clear sent log for this event (DANGER: causes re-sends).")

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("   FIND YOUR MATCH -- KALENJIN TAKE OVER EVENT BROADCAST")
    logger.info("   Event ID: %s | URL: %s/events/%s", EVENT_ID, args.server_url, EVENT_ID)
    logger.info("=" * 70)

    # 1. RESET LOGS IF REQUESTED
    if args.reset_sent:
        initialize_firebase()
        db.reference(f"event_broadcast_logs/{EVENT_ID}").delete()
        logger.warning("⚠️ RESET COMPLETE: Cleared sent history for %s. All users are now eligible again.", EVENT_ID)
        return

    # 2. STATS CHECK
    if args.stats:
        candidates, already_sent_count = get_recipients(EVENT_ID)
        logger.info("-" * 50)
        logger.info("Broadcast Progress for %s:", EVENT_ID)
        logger.info("Already Delivered : %d users", already_sent_count)
        logger.info("Remaining Pending : %d users", len(candidates))
        logger.info("-" * 50)
        return

    # 3. TEST MODE
    if args.test:
        send_test_preview(args.test.strip(), via_server=args.via_server, base_url=args.server_url)
        return

    # 4. DRY RUN
    if args.dry_run:
        candidates, already_sent_count = get_recipients(EVENT_ID)
        logger.info("\n--- [DRY RUN PREVIEW: FIRST 20 OF %d PENDING CANDIDATES] ---", len(candidates))
        for idx, u in enumerate(candidates[:20], 1):
            logger.info(f"[{idx:03d}/{len(candidates):03d}] UID: {u['uid'][:10]}... | {u['name']} <{u['email']}>")
        if len(candidates) > 20:
            logger.info("... and %d more registered users ready to receive the event email.", len(candidates) - 20)
        logger.info("--- END OF DRY RUN (No emails dispatched) ---")
        return

    # 5. DISPATCH VIA SERVER (RECOMMENDED)
    if args.via_server:
        run_via_server_batches(
            base_url=args.server_url,
            batch_size=args.batch_size,
            delay_between_batches=args.delay,
            limit=args.limit
        )
        return

    # 6. LOCAL SMTP DISPATCH
    candidates, _ = get_recipients(EVENT_ID)
    if args.limit and args.limit < len(candidates):
        candidates = candidates[:args.limit]

    logger.info("Dispatching %d emails via local SMTP with %.2fs delay...", len(candidates), args.delay)
    sent_count = 0
    failed_count = 0
    event_url = f"{args.server_url}/events/{EVENT_ID}"
    now_eat = datetime.now(EAT)

    for idx, user in enumerate(candidates, 1):
        email = user["email"]
        name = user["name"]
        uid = user["uid"]
        logger.info(f"[{idx}/{len(candidates)}] Sending to {name} <{email}>...")

        ok = send_kalenjin_takeover_email(email, name, event_url)
        if ok:
            sent_count += 1
            db.reference(f"event_broadcast_logs/{EVENT_ID}/{uid}").set({
                "sent_at": now_eat.isoformat(),
                "email": email,
                "name": name
            })
            logger.info(f"  -> ✅ Delivered to {email}")
        else:
            failed_count += 1
            logger.warning(f"  -> ❌ Failed to deliver to {email}")

        if idx < len(candidates):
            time.sleep(args.delay)

    logger.info("=" * 70)
    logger.info("  LOCAL BROADCAST COMPLETE")
    logger.info("  Delivered : %d", sent_count)
    logger.info("  Failed    : %d", failed_count)
    logger.info("  Log file  : %s", log_filename)
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
