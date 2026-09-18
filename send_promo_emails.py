import os, sys, time, logging, textwrap
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from email_service import _send_email, SENDER_NAME_DEFAULT

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger("promo_mailer")
EMAIL_DELAY_SECONDS = 1.5

def send_update_promo_email(recipient_email, recipient_name):
    subject = "🚀 Massive System Updates + 2-Day FREE Premium Access!"
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},

        We've just pushed a massive update to Find Your Match! The Discover Students page has been moved to the very top for better engagement, and we've refined our matching algorithms.

        To celebrate these updates and facilitate you finding your perfect match, we are offering EVERYONE a 2-Day Free Premium Access to the system!

        ⏳ The free offer ends this Friday at 12:00 PM.

        Please make sure to log in, update your profile (add photos and details), and start connecting right away.

        Update your profile here: https://mmust-dating-site.firebaseapp.com/profile

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
                
                <div style="background: linear-gradient(135deg, #720000 0%, #E60026 100%); padding: 50px 30px; text-align: center;">
                    <div style="font-size: 52px; margin-bottom: 15px;">🚀</div>
                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.3;">
                        System Updates & Free Access!
                    </h1>
                </div>

                <div style="padding: 40px 35px;">
                    <p style="font-size: 17px; color: #333; line-height: 1.7; margin-top: 0;">
                        Hello <strong style="color: #720000;">{recipient_name}</strong>,
                    </p>
                    <p style="font-size: 16px; color: #555; line-height: 1.7;">
                        We've just pushed massive updates to the system! The <strong>Discover Students</strong> section is now front-and-center to maximize your engagements, alongside many other background improvements.
                    </p>
                    
                    <div style="background: #fff8e6; border-left: 4px solid #f59e0b; padding: 20px; border-radius: 8px; margin: 25px 0;">
                        <h2 style="color: #b45309; font-size: 18px; margin: 0 0 10px 0;">🎁 2-Day FREE Premium Access</h2>
                        <p style="margin: 0; font-size: 15px; color: #92400e; line-height: 1.6;">
                            To help you find your perfect match with these new features, we are unlocking the system for everyone! This 100% free access will automatically expire on <strong>Friday at 12:00 PM</strong>.
                        </p>
                    </div>

                    <p style="font-size: 16px; color: #555; line-height: 1.7; margin-bottom: 30px;">
                        Make the most of this time! <strong>Update your profile</strong> with fresh photos and a catchy bio so others can discover you easily.
                    </p>

                    <div style="text-align: center;">
                        <a href="https://mmust-dating-site.firebaseapp.com/profile" style="display: inline-block; background-color: #E60026; color: white; text-decoration: none; padding: 16px 32px; border-radius: 12px; font-weight: bold; font-size: 16px; box-shadow: 0 4px 15px rgba(230,0,38,0.3);">
                            Update My Profile Now
                        </a>
                    </div>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def run():
    logger.info("=" * 60)
    logger.info("  FYM Promo Mailer - Starting Up")
    logger.info("=" * 60)

    initialize_firebase()
    all_profiles = get_all_profiles()

    if not all_profiles:
        logger.error("No profiles found. Aborting.")
        return

    logger.info(f"Fetched {len(all_profiles)} profiles total.")
    
    # Optional: Send to just a subset if testing, but user asked for ALL members
    target_users = all_profiles

    sent = failed = 0

    logger.info("Sending Promo Emails ...")
    for idx, user in enumerate(target_users, 1):
        name  = user.get("name") or user.get("username") or "there"
        email = user.get("email", "").strip()
        
        if not email:
            logger.warning(f"[{idx}/{len(target_users)}] Skipping {name} - no email.")
            failed += 1
            continue
            
        if send_update_promo_email(email, name):
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
    run()
