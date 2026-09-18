"""
send_test_match_email.py
========================
Sends a real Monday + Friday test match email immediately 
to verify the SMTP connection and email templates work.
Run: python send_test_match_email.py
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Validate env vars before anything ─────────────────────────────────────────
MAIL_SERVER   = os.getenv("MAIL_SERVER")
MAIL_PORT     = os.getenv("MAIL_PORT")
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

print("=" * 60)
print("FYM — Weekly Match Email Test")
print("=" * 60)
print(f"  MAIL_SERVER   : {MAIL_SERVER}")
print(f"  MAIL_PORT     : {MAIL_PORT}")
print(f"  MAIL_USERNAME : {MAIL_USERNAME}")
print(f"  MAIL_PASSWORD : {'*' * len(MAIL_PASSWORD) if MAIL_PASSWORD else 'MISSING'}")
print()

if not all([MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD]):
    print("❌ ERROR: Missing MAIL_SERVER, MAIL_USERNAME, or MAIL_PASSWORD in .env!")
    exit(1)

# ── Import and call the email functions ───────────────────────────────────────
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.email_service import send_monday_matches_email, send_friday_matches_email

# Fake match data (realistic example)
DEMO_MATCHES = [
    {
        "id": "DEMO_001",
        "name": "Achieng Anyango",
        "course": "SAB/B/01-05000/2023",
        "institution": "MMUST",
        "bio": "Software Engineering student who loves hiking and photography.",
        "phone": "254700000001",
        "email": "achieng.demo@findyourmatch.co.ke",
        "zodiac": "Leo",
        "mbti": "ENFJ",
        "compatibility": 91,
    },
    {
        "id": "DEMO_002",
        "name": "Wanjiru Kamau",
        "course": "SAB/C/01-05001/2022",
        "institution": "KU",
        "bio": "Chemistry student. Bookworm, foodie, and terrible at FIFA.",
        "phone": "254700000002",
        "email": "wanjiru.demo@findyourmatch.co.ke",
        "zodiac": "Virgo",
        "mbti": "INFP",
        "compatibility": 83,
    },
    {
        "id": "DEMO_003",
        "name": "Auma Ochieng",
        "course": "MED/A/01-05002/2021",
        "institution": "UoN",
        "bio": "Medicine student, basketball player, coffee addict.",
        "phone": "254700000003",
        "email": "auma.demo@findyourmatch.co.ke",
        "zodiac": "Scorpio",
        "mbti": "ISTJ",
        "compatibility": 76,
    },
]

# Send to the noreply address itself as a loopback test
TEST_RECIPIENT = MAIL_USERNAME
TEST_NAME      = "Test User"

print(f"Sending Monday test email to: {TEST_RECIPIENT}")
ok_mon = send_monday_matches_email(
    recipient_email=TEST_RECIPIENT,
    recipient_name=TEST_NAME,
    perfect_matches=DEMO_MATCHES
)
if ok_mon:
    print("  ✅ Monday Love Sheet email SENT successfully!")
else:
    print("  ❌ Monday Love Sheet email FAILED. Check your SMTP credentials / server.")

print()
print(f"Sending Friday test email to: {TEST_RECIPIENT}")
ok_fri = send_friday_matches_email(
    recipient_email=TEST_RECIPIENT,
    recipient_name=TEST_NAME,
    perfect_matches=DEMO_MATCHES
)
if ok_fri:
    print("  ✅ Friday Perfect Match Sheet email SENT successfully!")
else:
    print("  ❌ Friday Perfect Match Sheet email FAILED. Check your SMTP credentials / server.")

print()
print("Done. Check your inbox at:", TEST_RECIPIENT)
