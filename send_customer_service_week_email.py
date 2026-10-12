import os, sys, time, logging, textwrap
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from email_service import _send_email, SENDER_NAME_DEFAULT

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("cs_week_mailer")
EMAIL_DELAY_SECONDS = 1.5
BASE_URL = os.getenv("BASE_URL", "https://findyourmatch.co.ke").rstrip("/")

def send_cs_week_email(recipient_email, recipient_name):
    subject = "🎉 Happy Customer Service Week from Find Your Match!"
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},

        Happy Customer Service Week! 🎉

        We want to take a moment to celebrate YOU. Thank you for your continued support and for being such an important part of our journey at Find Your Match.

        We also want to remind you that your perfect matches are right here waiting for you! Keep swiping and connecting.

        🚀 Exciting Updates Rolling Out:
        We are introducing new system features very soon! You will get access to:
        - Direct interactions with sponsors.
        - A perfect online club experience to hang out, chat, and mingle.
        - And much more to make your experience incredible!

        Our team is dedicated to providing you with the best possible experience. If there is anything we can ever do to improve, please don't hesitate to reach out.

        Warm regards,
        The {SENDER_NAME_DEFAULT} Team 💌
    """)

    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 24px; overflow: hidden; box-shadow: 0 15px 40px rgba(114,0,0,0.10);">
                
                <!-- LOGO HEADER -->
                <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                    <img src="{BASE_URL}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 220px; height: auto; display: block; margin: 0 auto;">
                </div>

                <div style="background: linear-gradient(135deg, #720000 0%, #E60026 100%); padding: 40px 30px; text-align: center;">
                    <div style="font-size: 52px; margin-bottom: 15px;">🎉</div>
                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.3;">
                        Happy Customer Service Week!
                    </h1>
                </div>

                <div style="padding: 40px 35px;">
                    <p style="font-size: 17px; color: #333; line-height: 1.7; margin-top: 0;">
                        Hello <strong style="color: #720000;">{recipient_name}</strong>,
                    </p>
                    <p style="font-size: 16px; color: #555; line-height: 1.7;">
                        We want to take a moment to celebrate YOU. Thank you for your continued support and for being such an important part of our journey at <strong>Find Your Match</strong>.
                    </p>
                    
                    <p style="font-size: 16px; color: #555; line-height: 1.7;">
                        We also want to remind you that <strong>your perfect matches are right here waiting for you!</strong> Jump back in and spark a new connection today.
                    </p>

                    <div style="background: #e6f7ff; border-left: 4px solid #1890ff; padding: 20px; border-radius: 8px; margin: 25px 0;">
                        <h2 style="color: #0050b3; font-size: 18px; margin: 0 0 10px 0;">🚀 Exciting New Features Rolling Out</h2>
                        <ul style="margin: 0; font-size: 15px; color: #003a8c; line-height: 1.6; padding-left: 20px;">
                            <li style="margin-bottom: 8px;"><strong>Direct Sponsor Interactions:</strong> You will soon be exposed to direct interactions with sponsors!</li>
                            <li style="margin-bottom: 8px;"><strong>Perfect Online Club:</strong> Join an exclusive online club to mingle, chat, and connect in an entirely new way.</li>
                            <li><strong>More Surprises:</strong> Stay tuned as we roll out these game-changing features.</li>
                        </ul>
                    </div>
                    
                    <div style="background: #fff8e6; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; margin: 25px 0;">
                        <h2 style="color: #b45309; font-size: 18px; margin: 0 0 10px 0;">🌟 You Make Us Better</h2>
                        <p style="margin: 0; font-size: 15px; color: #92400e; line-height: 1.6;">
                            Our team is dedicated to providing you with the best possible experience. If there is anything we can ever do to improve, please don't hesitate to reach out. We love hearing from you!
                        </p>
                    </div>

                    <div style="text-align: center; margin-top: 35px;">
                        <a href="https://www.findyourmatch.co.ke/login" style="display: inline-block; background-color: #E60026; color: white; text-decoration: none; padding: 16px 32px; border-radius: 12px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(230,0,38,0.3);">
                            Find Your Matches Now
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def run(dry_run=False, test_email=None, limit=None):
    logger.info("=" * 60)
    logger.info(f"  FYM CS Week Mailer - Starting Up {'[DRY RUN]' if dry_run else ''}")
    logger.info("=" * 60)

    initialize_firebase()
    all_profiles = get_all_profiles()

    if not all_profiles:
        logger.error("No profiles found. Aborting.")
        return

    logger.info(f"Fetched {len(all_profiles)} profiles total.")
    
    if test_email:
        logger.info(f"Test mode active: Overriding target recipient to {test_email}")
        target_users = [{"id": "test_user", "name": "Valued User", "email": test_email}]
    else:
        target_users = [
            u for u in all_profiles 
            if (u.get("email") or "").strip() 
            and not u.get("is_banned") 
            and not u.get("email_opt_out")
        ]

    if limit and limit > 0:
        logger.info(f"Limiting execution to first {limit} users.")
        target_users = target_users[:limit]

    sent = failed = 0

    logger.info("Sending Customer Service Week Emails ...")
    logger.info(f"Targeting {len(target_users)} users.")
    for idx, user in enumerate(target_users, 1):
        name  = user.get("name") or user.get("username") or "there"
        email = user.get("email", "").strip()
        
        if not email:
            logger.warning(f"[{idx}/{len(target_users)}] Skipping {name} - no email.")
            failed += 1
            continue
            
        if dry_run:
            logger.info(f"[{idx}/{len(target_users)}] [DRY RUN] Would send -> {name} <{email}>")
            sent += 1
            continue

        if send_cs_week_email(email, name):
            logger.info(f"[{idx}/{len(target_users)}] Sent -> {name} <{email}>")
            sent += 1
        else:
            logger.error(f"[{idx}/{len(target_users)}] FAILED -> {name} <{email}>")
            failed += 1
            
        time.sleep(EMAIL_DELAY_SECONDS)

    logger.info("=" * 60)
    logger.info("  BROADCAST COMPLETE")
    logger.info(f"  Sent: {sent}   Failed: {failed}")
    logger.info("=" * 60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Send Customer Service Week Broadcast Emails")
    parser.add_argument("--dry-run", action="store_true", help="Preview recipients without sending")
    parser.add_argument("--test-email", type=str, default=None, help="Send a single test email to this address")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of emails to send")
    args = parser.parse_args()

    run(dry_run=args.dry_run, test_email=args.test_email, limit=args.limit)
