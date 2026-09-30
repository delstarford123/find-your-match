"""
send_apology_emails.py
Find Your Match -- Login System Apology Email Broadcaster

Sends the emergency apology email to ALL users regarding the recent login system interruption.

Run from the project root:
  .venv\Scripts\python send_apology_emails.py

Dry-run (preview without sending):
  .venv\Scripts\python send_apology_emails.py --dry-run
"""

import os, sys, time, logging, argparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from email_service import send_apology_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("apology_mailer")

# Delay between sends to avoid SMTP rate limits (seconds)
EMAIL_DELAY_SECONDS = 2.0


def run(dry_run=False):
    logger.info("=" * 62)
    logger.info("  FIND YOUR MATCH -- Login System Apology Email")
    if dry_run:
        logger.info("  *** DRY RUN -- no emails will be sent ***")
    logger.info("=" * 62)

    initialize_firebase()
    logger.info("Fetching all user profiles from Firebase ...")
    all_profiles = get_all_profiles()
    
    if not all_profiles:
        logger.warning("No profiles found in the database. Exiting.")
        return
        
    total_users = len(all_profiles)
    logger.info(f"Found {total_users} total profiles.")

    # Filter out users without valid emails and remove duplicate emails
    target_users = []
    seen_emails = set()
    
    for profile in all_profiles:
        if isinstance(profile, dict):
            email = profile.get("email", "").strip().lower()
            if email and "@" in email and email not in seen_emails:
                seen_emails.add(email)
                target_users.append(profile)

    target_users = [u for u in target_users if u.get("email", "").strip().lower() == "delstarfordisaiah@gmail.com"]
    logger.info(f"Filtered to {len(target_users)} users with valid emails.")
    logger.info("-" * 62)

    success_count = 0
    fail_count = 0

    START_INDEX = 1  # For test send

    for idx, user in enumerate(target_users, start=1):
        if idx < START_INDEX:
            continue
            
        email = user.get("email", "").strip()
        name = user.get("name", "User").strip()
        
        logger.info(f"[{idx}/{len(target_users)}] Preparing to send to {email} ...")
        
        if dry_run:
            logger.info(f"  [DRY RUN] Would send apology email to {name} <{email}>")
            success_count += 1
        else:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    success = send_apology_email(email, name)
                    if success:
                        logger.info(f"  [SUCCESS] Email sent to {email}")
                        success_count += 1
                        break
                    else:
                        logger.error(f"  [FAIL] Failed to send email to {email}")
                        if attempt == max_retries - 1:
                            fail_count += 1
                        else:
                            time.sleep(5)
                except Exception as e:
                    logger.error(f"  [ERROR] Exception sending to {email}: {e}")
                    if "10054" in str(e) or attempt < max_retries - 1:
                        logger.info(f"  [RETRY] Connection dropped. Reconnecting in 10 seconds (Attempt {attempt+1}/{max_retries})...")
                        time.sleep(10)
                    else:
                        fail_count += 1
                        break
            
            # Sleep to prevent SMTP blocking
            time.sleep(EMAIL_DELAY_SECONDS)

    logger.info("=" * 62)
    logger.info(f"  BROADCAST COMPLETE")
    logger.info(f"  Total Sent:   {success_count}")
    logger.info(f"  Total Failed: {fail_count}")
    logger.info("=" * 62)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Broadcast Apology Email to All Users")
    parser.add_argument("--dry-run", action="store_true", help="Run without actually sending emails")
    args = parser.parse_args()
    
    run(dry_run=args.dry_run)
