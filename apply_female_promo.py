import os, sys, logging, argparse
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import initialize_firebase, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("female_promo")

OFFER_END_UTC  = datetime(2026, 10, 23, 23, 59, 59, tzinfo=timezone.utc)
PROMO_DAYS     = 30
PROMO_RECEIPT  = "FEMALE_PROMO_1MONTH_SEP2026"
DOMAIN         = "findyourmatch.co.ke"

def run(dry_run=False):
    now_utc = datetime.now(timezone.utc)
    logger.info("=" * 62)
    logger.info("  %s -- FEMALE FREE PROMO", DOMAIN.upper())
    logger.info("  Already-registered females -> 1 month (30 days) free")
    logger.info("  Offer valid until: %s UTC", OFFER_END_UTC.strftime("%Y-%m-%d"))
    if dry_run:
        logger.info("  *** DRY RUN -- no changes will be written ***")
    logger.info("=" * 62)

    if now_utc > OFFER_END_UTC:
        logger.error("The female promo offer ended on Oct 23 2026. Nothing to do.")
        return

    initialize_firebase()
    profiles_ref     = db.reference("profiles")
    profiles         = profiles_ref.get() or {}
    promo_expiry_dt  = now_utc + timedelta(days=PROMO_DAYS)
    promo_expiry_str = promo_expiry_dt.isoformat()

    logger.info("Promo expiry will be: %s", promo_expiry_str)
    logger.info("Total profiles      : %d", len(profiles))
    logger.info("-" * 62)

    granted = skipped_gender = skipped_better = errors = 0

    for uid, user in profiles.items():
        if not isinstance(user, dict):
            continue
        if user.get("gender", "").strip().lower() != "female":
            skipped_gender += 1
            continue

        name = user.get("name", uid)
        has_better_sub = False
        curr_exp = user.get("subscription_expiry", "")
        if user.get("is_paid") and curr_exp:
            try:
                if datetime.fromisoformat(curr_exp.replace("Z", "+00:00")) > promo_expiry_dt:
                    has_better_sub = True
            except Exception:
                pass

        if has_better_sub:
            logger.info("  SKIP  %s (already has longer sub until %s)", name, curr_exp[:10])
            skipped_better += 1
            continue

        logger.info("  GRANT %s --> free until %s", name, promo_expiry_str[:10])
        if not dry_run:
            try:
                profiles_ref.child(uid).update({
                    "is_paid":              True,
                    "subscription_expiry":  promo_expiry_str,
                    "subscription_package": "gold",
                    "last_payment_receipt": PROMO_RECEIPT,
                })
                granted += 1
            except Exception as e:
                logger.error("  ERROR %s: %s", uid, e)
                errors += 1
        else:
            granted += 1

    logger.info("=" * 62)
    logger.info("  %s", "DRY RUN -- nothing written." if dry_run else "DONE.")
    logger.info("  Granted (or would grant): %d female users", granted)
    logger.info("  Skipped (better sub)    : %d", skipped_better)
    logger.info("  Skipped (not female)    : %d", skipped_gender)
    if errors:
        logger.warning("  Errors                  : %d", errors)
    logger.info("=" * 62)
    logger.info("  New female signups before Oct 23 2026 automatically")
    logger.info("  get 2 months free on email verification. No action needed.")
    logger.info("=" * 62)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grant 1-month free to existing female users on findyourmatch.co.ke")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Firebase")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
