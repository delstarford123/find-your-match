"""
send_campaign_emails.py
FYM Campaign Email Broadcaster - September 2025 Online Event
Run from the project root:  python send_campaign_emails.py
"""

import os, sys, time, logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from email_service import send_male_campaign_email, send_female_campaign_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("campaign_mailer")
EMAIL_DELAY_SECONDS = 1.5

def run():
    logger.info("=" * 60)
    logger.info("  FYM Campaign Email Broadcaster - Starting Up")
    logger.info("=" * 60)

    initialize_firebase()
    logger.info("Fetching all user profiles from Firebase ...")
    all_profiles = get_all_profiles()

    if not all_profiles:
        logger.error("No profiles found. Aborting.")
        return

    logger.info(f"Fetched {len(all_profiles)} profiles total.")

    males   = [p for p in all_profiles if str(p.get("gender", "")).strip().lower() == "male"]
    females = [p for p in all_profiles if str(p.get("gender", "")).strip().lower() == "female"]

    logger.info(f"Males: {len(males)}   Females: {len(females)}")
    logger.info("-" * 60)

    male_sent = male_failed = female_sent = female_failed = 0

    logger.info("Sending to MALES ...")
    for idx, user in enumerate(males, 1):
        name  = user.get("name") or user.get("username") or "there"
        email = user.get("email", "").strip()
        if not email:
            logger.warning(f"[{idx}/{len(males)}] Skipping {name} - no email.")
            male_failed += 1
            continue
        if send_male_campaign_email(email, name):
            logger.info(f"[{idx}/{len(males)}] Sent -> {name} <{email}>")
            male_sent += 1
        else:
            logger.error(f"[{idx}/{len(males)}] FAILED -> {name} <{email}>")
            male_failed += 1
        time.sleep(EMAIL_DELAY_SECONDS)

    logger.info("-" * 60)
    logger.info("Sending to FEMALES ...")
    for idx, user in enumerate(females, 1):
        name  = user.get("name") or user.get("username") or "there"
        email = user.get("email", "").strip()
        if not email:
            logger.warning(f"[{idx}/{len(females)}] Skipping {name} - no email.")
            female_failed += 1
            continue
        if send_female_campaign_email(email, name):
            logger.info(f"[{idx}/{len(females)}] Sent -> {name} <{email}>")
            female_sent += 1
        else:
            logger.error(f"[{idx}/{len(females)}] FAILED -> {name} <{email}>")
            female_failed += 1
        time.sleep(EMAIL_DELAY_SECONDS)

    logger.info("=" * 60)
    logger.info("  BROADCAST COMPLETE - SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Males   -> Sent: {male_sent}   Failed: {male_failed}")
    logger.info(f"  Females -> Sent: {female_sent}   Failed: {female_failed}")
    logger.info(f"  Total sent: {male_sent + female_sent}  |  Total failed: {male_failed + female_failed}")
    logger.info("=" * 60)

if __name__ == "__main__":
    run()
