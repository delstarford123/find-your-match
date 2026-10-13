#!/usr/bin/env python3
"""
send_female_profile_reminder.py
--------------------------------
Professional Email Campaign targeting female users on Find Your Match (findyourmatch.co.ke).
Encourages members to complete their profile (upload real photos, write an authentic bio, and add details).

Usage:
  # 1. Dry run (preview list of female recipients and status without sending):
  python send_female_profile_reminder.py --dry-run

  # 2. Test send to your own inbox first:
  python send_female_profile_reminder.py --test delstarfordisaiah@gmail.com

  # 3. Live run (sends to all females with polite rate-limiting):
  python send_female_profile_reminder.py

  # 4. Target only those who currently have incomplete profiles:
  python send_female_profile_reminder.py --only-incomplete
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime
import textwrap
from dotenv import load_dotenv

# Load local environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import initialize_firebase, db
from email_service import _send_email, SENDER_NAME_DEFAULT

# Setup logging
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/female_profile_reminder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_filename, encoding="utf-8")
    ]
)
logger = logging.getLogger("female_reminder_mailer")

BASE_URL = os.getenv("BASE_URL", "https://findyourmatch.co.ke").rstrip("/")
PROFILE_URL = f"{BASE_URL}/profile"
SUPPORT_EMAIL = "support@findyourmatch.co.ke"


def build_email_content(recipient_name: str):
    """
    Constructs both plain text and premium, responsive HTML email content.
    """
    # Clean up name display
    first_name = recipient_name.strip().split()[0].title() if recipient_name else "there"
    full_display_name = recipient_name.strip().title() if recipient_name else "Valued Member"

    subject = f"✨ {first_name}, put your best self forward: Complete your profile on Find Your Match!"

    text_content = textwrap.dedent(f"""\
        Hello {full_display_name},

        We hope you are having a wonderful week!

        At Find Your Match, our goal is to help you connect with genuine, compatible campus matches who appreciate the real you.

        Did you know? Profiles with an authentic photo and a personalized bio receive up to 5x more meaningful match requests! 

        To help you get the best experience and attract genuine connections, we kindly encourage you to take two minutes to update your profile:

        1. 📸 Add a Clear Profile Photo: A warm, clear photo makes an unforgettable first impression.
        2. ✍️ Write an Engaging Bio: Share what you're passionate about, your hobbies, or what makes you smile.
        3. 🎓 Verify Your Campus Details: Help students from your institution connect with you authentically.

        👉 Update your profile now:
        {PROFILE_URL}

        If you have already updated your details recently, thank you for being an active part of our community!

        Warm regards,
        The {SENDER_NAME_DEFAULT} Team
        Website: {BASE_URL}
        Support: {SUPPORT_EMAIL}
    """)

    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; background-color: #f7f5f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
            
            <!-- OUTER WRAPPER -->
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f7f5f8; padding: 30px 10px;">
                <tr>
                    <td align="center">
                        
                        <!-- MAIN CONTAINER -->
                        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="max-width: 600px; background-color: #ffffff; border-radius: 24px; overflow: hidden; box-shadow: 0 20px 45px rgba(136, 19, 55, 0.08); border: 1px solid #f1e7ed;">
                            
                            <!-- LOGO HEADER -->
                            <tr>
                                <td align="center" style="padding: 26px 20px 20px; background-color: #ffffff; border-bottom: 1px solid #f8eef3;">
                                    <img src="{BASE_URL}/static/img/icon-512.png" alt="Find Your Match" width="140" style="width: 140px; max-width: 140px; height: auto; display: block; margin: 0 auto; border-radius: 12px;">
                                </td>
                            </tr>

                            <!-- HERO BANNER -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #881337 0%, #BE123C 55%, #E11D48 100%); padding: 45px 35px; text-align: center;">
                                    <div style="display: inline-block; background-color: rgba(255,255,255,0.20); color: #ffffff; padding: 6px 16px; border-radius: 50px; font-size: 13px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; margin-bottom: 16px;">
                                        🌸 Profile Spotlight
                                    </div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 26px; font-weight: 800; line-height: 1.3; letter-spacing: -0.5px;">
                                        Put Your Best Self Forward
                                    </h1>
                                    <p style="color: rgba(255, 255, 255, 0.92); margin: 12px auto 0; font-size: 15px; line-height: 1.6; max-width: 480px;">
                                        Make an unforgettable first impression and attract the campus matches you truly deserve.
                                    </p>
                                </td>
                            </tr>

                            <!-- MAIN BODY -->
                            <tr>
                                <td style="padding: 40px 35px 30px;">
                                    
                                    <p style="font-size: 17px; color: #1f2937; line-height: 1.6; margin: 0 0 16px; font-weight: 600;">
                                        Hello <span style="color: #BE123C;">{full_display_name}</span>,
                                    </p>

                                    <p style="font-size: 15px; color: #4b5563; line-height: 1.7; margin: 0 0 24px;">
                                        We're thrilled to have you in the <strong>Find Your Match</strong> community! Whether you are looking for engaging conversations, campus friendship, or a special connection, being noticed starts with a standout profile.
                                    </p>

                                    <!-- STAT CALLOUT BOX -->
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #fff1f2; border-left: 4px solid #E11D48; border-radius: 12px; margin-bottom: 30px;">
                                        <tr>
                                            <td style="padding: 18px 22px;">
                                                <p style="margin: 0; font-size: 14px; color: #881337; line-height: 1.6; font-weight: 600;">
                                                    💡 <strong>Quick Fact:</strong> Profiles featuring an authentic portrait photo and a personalized bio receive over <strong>5x more quality match requests</strong>!
                                                </p>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- 3 EASY STEPS CARDS -->
                                    <h2 style="font-size: 16px; color: #111827; margin: 0 0 18px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
                                        3 Easy Steps to Perfect Your Profile:
                                    </h2>

                                    <!-- Step 1 -->
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 14px; background-color: #faf7f9; border: 1px solid #f3e8ee; border-radius: 14px;">
                                        <tr>
                                            <td width="48" valign="top" style="padding: 16px 0 16px 18px; font-size: 26px;">
                                                📸
                                            </td>
                                            <td style="padding: 16px 18px 16px 10px;">
                                                <div style="font-size: 15px; font-weight: 700; color: #1f2937; margin-bottom: 4px;">
                                                    Upload a Clear Profile Photo
                                                </div>
                                                <div style="font-size: 13px; color: #6b7280; line-height: 1.5;">
                                                    Show off your genuine smile. Clear portraits immediately build trust and captivate attention.
                                                </div>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- Step 2 -->
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 14px; background-color: #faf7f9; border: 1px solid #f3e8ee; border-radius: 14px;">
                                        <tr>
                                            <td width="48" valign="top" style="padding: 16px 0 16px 18px; font-size: 26px;">
                                                ✍️
                                            </td>
                                            <td style="padding: 16px 18px 16px 10px;">
                                                <div style="font-size: 15px; font-weight: 700; color: #1f2937; margin-bottom: 4px;">
                                                    Write an Authentic Bio
                                                </div>
                                                <div style="font-size: 13px; color: #6b7280; line-height: 1.5;">
                                                    Share your passions, vibe, or favorite hobbies. Give someone a great conversation starter!
                                                </div>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- Step 3 -->
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom: 28px; background-color: #faf7f9; border: 1px solid #f3e8ee; border-radius: 14px;">
                                        <tr>
                                            <td width="48" valign="top" style="padding: 16px 0 16px 18px; font-size: 26px;">
                                                🎓
                                            </td>
                                            <td style="padding: 16px 18px 16px 10px;">
                                                <div style="font-size: 15px; font-weight: 700; color: #1f2937; margin-bottom: 4px;">
                                                    Update Your Campus & Details
                                                </div>
                                                <div style="font-size: 13px; color: #6b7280; line-height: 1.5;">
                                                    Keep your institution and interests up to date to discover nearby campus students instantly.
                                                </div>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- CTA BUTTON -->
                                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin: 25px 0;">
                                        <tr>
                                            <td align="center">
                                                <a href="{PROFILE_URL}" target="_blank" style="display: inline-block; background: linear-gradient(135deg, #BE123C 0%, #E11D48 100%); color: #ffffff; text-decoration: none; padding: 18px 38px; border-radius: 50px; font-weight: 700; font-size: 16px; letter-spacing: 0.3px; box-shadow: 0 8px 24px rgba(225, 29, 72, 0.35); text-align: center;">
                                                    ✨ Update My Profile Now &rarr;
                                                </a>
                                            </td>
                                        </tr>
                                    </table>

                                    <!-- FALLBACK LINK -->
                                    <div style="background-color: #f9fafb; border-radius: 12px; padding: 14px 18px; text-align: center; margin-top: 25px;">
                                        <p style="margin: 0; font-size: 12px; color: #6b7280; line-height: 1.5;">
                                            Button not clicking? Copy and paste this link into your browser:<br>
                                            <a href="{PROFILE_URL}" style="color: #BE123C; word-break: break-all; font-weight: 600;">{PROFILE_URL}</a>
                                        </p>
                                    </div>

                                </td>
                            </tr>

                            <!-- FOOTER -->
                            <tr>
                                <td style="background-color: #faf7f9; padding: 30px 35px; border-top: 1px solid #f1e7ed; text-align: center;">
                                    <p style="margin: 0 0 10px; font-size: 13px; color: #6b7280; font-weight: 500;">
                                        Need any assistance? We're here to help!
                                    </p>
                                    <p style="margin: 0 0 18px; font-size: 13px;">
                                        <a href="mailto:{SUPPORT_EMAIL}" style="color: #BE123C; text-decoration: none; font-weight: 600;">{SUPPORT_EMAIL}</a>
                                        &nbsp;•&nbsp;
                                        <a href="{BASE_URL}" style="color: #4b5563; text-decoration: none;">{BASE_URL}</a>
                                    </p>
                                    <p style="margin: 0; font-size: 11px; color: #9ca3af; line-height: 1.5;">
                                        &copy; {datetime.now().year} Find Your Match. All rights reserved.<br>
                                        You received this email because you are a registered member of Find Your Match.
                                    </p>
                                </td>
                            </tr>

                        </table>
                        <!-- END MAIN CONTAINER -->

                    </td>
                </tr>
            </table>

        </body>
        </html>
    """)

    return subject, text_content, html_content


def get_female_candidates(only_incomplete: bool = False):
    """
    Fetches all female users from Firebase and checks profile completion.
    """
    initialize_firebase()
    users = db.reference("profiles").get() or {}

    candidates = []

    for uid, data in users.items():
        if not isinstance(data, dict):
            continue

        gender = str(data.get("gender", "")).strip().lower()
        if gender != "female":
            continue

        email = str(data.get("email", "")).strip()
        if not email or "@" not in email:
            continue

        name = str(data.get("name", "Student")).strip()
        bio = str(data.get("bio", "")).strip()
        img = str(data.get("img", "")).strip()

        # Check completeness
        has_default_bio = (not bio) or (bio.lower() == "hey! i just joined find your match.")
        has_default_photo = (not img) or ("default" in img.lower())

        is_incomplete = has_default_bio or has_default_photo

        if only_incomplete and not is_incomplete:
            continue

        candidates.append({
            "uid": uid,
            "name": name,
            "email": email,
            "phone": data.get("phone", "N/A"),
            "has_default_bio": has_default_bio,
            "has_default_photo": has_default_photo,
            "bio": bio[:40] + ("..." if len(bio) > 40 else ""),
            "img_set": not has_default_photo
        })

    return candidates


def main():
    parser = argparse.ArgumentParser(description="Send profile update reminder email to female users.")
    parser.add_argument("--dry-run", action="store_true", help="Preview target list without sending emails.")
    parser.add_argument("--test", type=str, help="Send a single test email to the specified address.")
    parser.add_argument("--only-incomplete", action="store_true", help="Only target ladies with missing photo or bio.")
    parser.add_argument("--delay", type=float, default=1.5, help="Delay in seconds between sends (default: 1.5s).")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of emails to send.")

    args = parser.parse_args()

    logger.info("=" * 65)
    logger.info("   FIND YOUR MATCH -- FEMALE PROFILE UPDATE CAMPAIGN")
    logger.info("   Target: Female Users | Domain: %s", BASE_URL)
    logger.info("=" * 65)

    # 1. TEST MODE
    if args.test:
        test_email = args.test.strip()
        logger.info("⚡ TEST MODE ACTIVATED: Sending 1 preview email to %s", test_email)
        subject, text_content, html_content = build_email_content("Test User")
        
        success = _send_email(
            recipient_email=test_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            sender_name="Find Your Match"
        )
        if success:
            logger.info("✅ Test email sent successfully to %s!", test_email)
            logger.info("Check your inbox and verify the layout and links.")
        else:
            logger.error("❌ Failed to send test email to %s. Check SMTP configuration in .env.", test_email)
        return

    # 2. FETCH CANDIDATES
    candidates = get_female_candidates(only_incomplete=args.only_incomplete)
    total_candidates = len(candidates)
    
    logger.info("Found %d female profiles matching criteria.", total_candidates)
    if args.limit and args.limit < total_candidates:
        candidates = candidates[:args.limit]
        logger.info("Capped to first %d recipients due to --limit flag.", len(candidates))

    # 3. DRY RUN MODE
    if args.dry_run:
        logger.info("\n--- [DRY RUN PREVIEW] ---")
        for idx, u in enumerate(candidates, 1):
            status_flags = []
            if u["has_default_photo"]:
                status_flags.append("NO_PHOTO")
            if u["has_default_bio"]:
                status_flags.append("NO_BIO")
            status_desc = ", ".join(status_flags) if status_flags else "PROFILE_COMPLETE"

            logger.info(
                f"[{idx:02d}/{len(candidates):02d}] {u['name']} <{u['email']}> | Status: [{status_desc}]"
            )
        logger.info("--- END OF DRY RUN (No emails were sent) ---")
        logger.info("To send emails for real, run: python send_female_profile_reminder.py")
        return

    # 4. CONFIRMATION PROMPT FOR SAFETY IF RUNNING LIVE
    if not candidates:
        logger.warning("No female candidates found to email.")
        return

    logger.info("Ready to dispatch %d emails with a %.1fs delay between each send.", len(candidates), args.delay)
    
    sent_count = 0
    failed_count = 0

    for idx, user in enumerate(candidates, 1):
        name = user["name"]
        email = user["email"]

        logger.info(f"[{idx}/{len(candidates)}] Sending to {name} <{email}>...")
        subject, text_content, html_content = build_email_content(name)

        try:
            success = _send_email(
                recipient_email=email,
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                sender_name="Find Your Match"
            )

            if success:
                sent_count += 1
                logger.info(f"  -> ✅ Delivered to {email}")
            else:
                failed_count += 1
                logger.warning(f"  -> ❌ Failed to deliver to {email}")

        except Exception as e:
            failed_count += 1
            logger.error(f"  -> ❌ Exception sending to {email}: {e}")

        # Rate limiting delay
        if idx < len(candidates):
            time.sleep(args.delay)

    logger.info("=" * 65)
    logger.info("  CAMPAIGN COMPLETE!")
    logger.info("  Total Attempted: %d", len(candidates))
    logger.info("  Delivered      : %d", sent_count)
    logger.info("  Failed         : %d", failed_count)
    logger.info("  Log file       : %s", log_filename)
    logger.info("=" * 65)


if __name__ == "__main__":
    main()
