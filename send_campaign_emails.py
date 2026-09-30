"""
send_campaign_emails.py
Find Your Match -- Female Free Access Promo Campaign Broadcaster
findyourmatch.co.ke

Sends the Sep 2026 female promo campaign email to ALL female users.
The email covers:
  1. 1 month FREE Premium (already registered) / 2 months (new signups)
  2. New platform features (opposite-gender filtering, scroll fix)
  3. Referral CTA -- invite your female friends

Run from the project root:
  .venv\\Scripts\\python send_campaign_emails.py

Dry-run (preview without sending):
  .venv\\Scripts\\python send_campaign_emails.py --dry-run
"""

import os, sys, time, logging, argparse
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from email_service import send_female_promo_campaign_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("campaign_mailer")

# Delay between sends to avoid SMTP rate limits (seconds)
EMAIL_DELAY_SECONDS = 2.0


def run(dry_run=False):
    logger.info("=" * 62)
    logger.info("  FIND YOUR MATCH -- Female Free Access Promo Campaign")
    logger.info("  findyourmatch.co.ke")
    if dry_run:
        logger.info("  *** DRY RUN -- no emails will be sent ***")
    logger.info("=" * 62)

    initialize_firebase()
    logger.info("Fetching all user profiles from Firebase ...")
    all_profiles = get_all_profiles()

    if not all_profiles:
        logger.error("No profiles found. Aborting.")
        return

    logger.info(f"Total profiles fetched: {len(all_profiles)}")

    # Filter to verified female users with a valid email
    females = [
        p for p in all_profiles
        if str(p.get("gender", "")).strip().lower() == "female"
        and p.get("is_verified")
        and p.get("email", "").strip()
    ]

    logger.info(f"Eligible female recipients: {len(females)}")
    logger.info("-" * 62)

    sent = failed = skipped = 0

    for idx, user in enumerate(females, 1):
        name  = (user.get("name") or user.get("username") or "there").strip()
        email = user.get("email", "").strip()
        first = name.split(" ")[0]

        if not email:
            logger.warning(f"  [{idx}/{len(females)}] SKIP {name} -- no email address")
            skipped += 1
            continue

        if dry_run:
            logger.info(f"  [{idx}/{len(females)}] WOULD SEND --> {first} <{email}>")
            sent += 1
            continue

        try:
            success = send_female_promo_campaign_email(email, name)
            if success:
                logger.info(f"  [{idx}/{len(females)}] SENT --> {first} <{email}>")
                sent += 1
            else:
                logger.error(f"  [{idx}/{len(females)}] FAILED --> {first} <{email}>")
                failed += 1
        except Exception as e:
            logger.error(f"  [{idx}/{len(females)}] ERROR {first} <{email}>: {e}")
            failed += 1

        # Polite delay to avoid tripping spam filters
        time.sleep(EMAIL_DELAY_SECONDS)

    logger.info("=" * 62)
    logger.info("  CAMPAIGN BROADCAST COMPLETE")
    logger.info("=" * 62)
    logger.info(f"  {'Would send' if dry_run else 'Sent'}    : {sent}")
    if not dry_run:
        logger.info(f"  Failed  : {failed}")
    logger.info(f"  Skipped : {skipped}  (no email or unverified)")
    logger.info(f"  Total   : {len(females)}")
    logger.info("=" * 62)
    if dry_run:
        logger.info("  DRY RUN COMPLETE -- run without --dry-run to send for real.")
    logger.info("=" * 62)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Send the Female Free Access Promo campaign email on findyourmatch.co.ke"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview recipients without sending any emails"
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
