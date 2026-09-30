import sys
import time
import os
from dotenv import load_dotenv

# Load environment variables so credentials are found in cron
load_dotenv()

try:
    from app.database import db
    from app.email_service import send_broadcast_email
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

def main():
    print("Fetching profiles...")
    profiles_ref = db.reference('profiles')
    all_profiles = profiles_ref.get()

    if not all_profiles:
        print("No profiles found.")
        return

    subject = "System Update, Exciting Improvements & Apology"
    message_body = (
        "We sincerely apologize for the recent system downtime, which was caused by an unexpected issue with our hosting servers. "
        "Our engineering team has worked diligently to resolve the problem and improve the overall stability of the platform for a better experience.\n\n"
        "The system is now fully restored and up and running. As part of this process, we have successfully verified all liable emails.\n\n"
        "We're also excited to share that we've made massive improvements to the Virtual Club! Expect a smoother, more engaging experience, and a stronger, more vibrant community waiting for you inside.\n\n"
        "We wish you a happy Tuesday! Your Perfect Match is here waiting for you. Thank you for your patience and continued support."
    )

    verified_count = 0
    email_count = 0
    skipped_count = 0

    for uid, user_data in all_profiles.items():
        if not isinstance(user_data, dict):
            continue

        is_verified = user_data.get('is_verified', False)
        apology_sent = user_data.get('apology_email_sent_v2', False)
        email = user_data.get('email')
        name = user_data.get('name', 'Valued User')

        # Automatically verify unverified users
        if not is_verified:
            db.reference(f'profiles/{uid}').update({'is_verified': True})
            verified_count += 1
            print(f"Verified user: {email or uid}")

        # Send alert email to all users
        if email:
            if apology_sent:
                print(f"Skipping {email}, already sent.")
                skipped_count += 1
                continue

            print(f"Sending email to {email}...")
            success = send_broadcast_email(email, name, subject, message_body)
            if success:
                # Mark as sent to avoid duplicates in case of cron retries
                db.reference(f'profiles/{uid}').update({'apology_email_sent_v2': True})
                email_count += 1
            else:
                print(f"Failed to send email to {email}")
            time.sleep(1) # Sleep to avoid rate limiting

    print(f"\nDone! Automatically verified {verified_count} accounts.")
    print(f"Sent alert emails to {email_count} users. Skipped {skipped_count} already sent.")

if __name__ == '__main__':
    main()
