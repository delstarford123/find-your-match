"""
broadcast_announcement.py
==========================
Sends a beautiful announcement email to all verified users.
Uses batched SMTP connections (reconnects every 20 emails)
to avoid SMTP server "please run connect() first" timeouts.

Run: python broadcast_announcement.py
"""

import os
import sys
import textwrap
import smtplib
import ssl
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, formatdate, make_msgid
from dotenv import load_dotenv

load_dotenv()

MAIL_SERVER   = os.getenv("MAIL_SERVER", "mail.findyourmatch.co.ke")
MAIL_PORT     = int(os.getenv("MAIL_PORT", 465))
MAIL_USERNAME = os.getenv("MAIL_USERNAME", "noreply@findyourmatch.co.ke")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "")
BASE_URL      = os.getenv("BASE_URL", "https://www.findyourmatch.co.ke").rstrip("/")
YEAR          = datetime.now().year

# Reconnect every N emails to avoid SMTP server timeouts
BATCH_SIZE = 15

print("=" * 65)
print("  FIND YOUR MATCH AI — Platform Announcement Broadcast")
print("=" * 65)
print(f"  Server      : {MAIL_SERVER}:{MAIL_PORT}")
print(f"  Sender      : {MAIL_USERNAME}")
print(f"  Batch size  : {BATCH_SIZE} emails per SMTP connection")
print()


def build_email(recipient_name, recipient_email):
    subject = "🚀 HUGE Updates on Find Your Match: New Login, 24/7 Club & Better Matches!"

    text_body = textwrap.dedent(f"""\
        Hello {recipient_name}!

        We've been hard at work behind the scenes listening to your feedback, and today we're rolling out some massive updates to make FIND YOUR MATCH faster, safer, and even more exciting!

        Here is what's new and waiting for you:

        ✨ 1. A Brand New, Faster Login System
        No more struggling to remember your registration number! We've upgraded our entire authentication system. You can now log in faster and more securely. (If you're a legacy user, don't worry—you can still log in with your old credentials, and we'll help you upgrade your account in a few simple clicks).

        📸 2. Complete Your Profile for Better Matches
        To keep the community safe and ensure you're matching with real students, we are now requiring all users to complete their profiles. If you haven't already, please upload your best photo and add a valid phone number.
        👉 Update Profile here: {BASE_URL}/dashboard

        🌙 3. The Comrades Club is Now Open 24/7!
        You asked, and we listened! We've completely removed the time restrictions on the club. The Comrades Club is now open 24/7. Drop in anytime, day or night, to chat, vibe, and mingle with the entire campus community with zero restrictions.

        🎯 4. Stricter, Smarter Matchmaking
        We've refined our AI matching algorithms! The system now strictly enforces opposite-gender filtering across the entire app. Your Swipes and "Perfect Matches" on the dashboard are now exclusively curated to show you exactly who you are looking for.
        👉 Start Swiping here: {BASE_URL}/swipe

        Ready to see the new updates in action? Jump back in, complete your profile, and let the AI find your perfect match.

        Stay safe and happy swiping,
        The FIND YOUR MATCH Team 💖

        (c) {YEAR} Delstarford Works. All rights reserved.
        Reply UNSUBSCRIBE to opt out.
    """)

    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#f4f1ff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
<div style="max-width:620px;margin:30px auto;background:white;border-radius:24px;overflow:hidden;box-shadow:0 20px 60px rgba(114,0,114,0.08);">

    <!-- HERO -->
    <div style="background:linear-gradient(135deg,#720000 0%,#E60026 55%,#ff6b6b 100%);padding:50px 30px 40px;text-align:center;">
        <div style="font-size:52px;margin-bottom:16px;">&#128140;</div>
        <h1 style="color:white;margin:0 0 10px;font-size:28px;font-weight:900;letter-spacing:-0.5px;line-height:1.3;">
            Big News from<br>FIND YOUR MATCH!
        </h1>
        <p style="color:rgba(255,255,255,0.88);font-size:16px;margin:0;font-weight:500;">
            A Brand New Login, 24/7 Club & Better Matches! 🚀
        </p>
    </div>

    <!-- CONTENT -->
    <div style="padding:40px 36px 10px;">
        <p style="font-size:16px;color:#333;line-height:1.6;margin-top:0;">
            Hello <strong>{recipient_name}</strong>,<br><br>
            We've been hard at work behind the scenes listening to your feedback, and today we're rolling out some massive updates to make <strong>FIND YOUR MATCH</strong> faster, safer, and even more exciting!
        </p>
        
        <h2 style="font-size:20px;font-weight:900;color:#111;margin:35px 0 20px;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #f0f0f0;padding-bottom:10px;">
            Here is what's new:
        </h2>

        <div style="display:flex;align-items:flex-start;gap:16px;margin-bottom:20px;background:#fef2f2;border-radius:16px;padding:18px;border-left:4px solid #ef4444;">
            <div style="font-size:26px;flex-shrink:0;">✨</div>
            <div>
                <div style="font-size:15px;font-weight:900;color:#991b1b;margin-bottom:4px;">1. A Brand New, Faster Login System</div>
                <div style="font-size:14px;color:#555;line-height:1.6;">
                    No more struggling to remember your registration number! We've upgraded our entire authentication system. You can now log in faster and more securely. (Legacy users can still log in normally to easily migrate their accounts).
                </div>
            </div>
        </div>

        <div style="display:flex;align-items:flex-start;gap:16px;margin-bottom:20px;background:#fff8f0;border-radius:16px;padding:18px;border-left:4px solid #f59e0b;">
            <div style="font-size:26px;flex-shrink:0;">📸</div>
            <div>
                <div style="font-size:15px;font-weight:900;color:#b45309;margin-bottom:4px;">2. Complete Your Profile for Better Matches</div>
                <div style="font-size:14px;color:#555;line-height:1.6;">
                    To keep the community safe, we now require all users to complete their profiles. If you haven't already, please upload your best photo and add a valid phone number via the dashboard.
                </div>
            </div>
        </div>

        <div style="display:flex;align-items:flex-start;gap:16px;margin-bottom:20px;background:#f0f9ff;border-radius:16px;padding:18px;border-left:4px solid #0ea5e9;">
            <div style="font-size:26px;flex-shrink:0;">🌙</div>
            <div>
                <div style="font-size:15px;font-weight:900;color:#0369a1;margin-bottom:4px;">3. The Comrades Club is Now Open 24/7!</div>
                <div style="font-size:14px;color:#555;line-height:1.6;">
                    You asked, and we listened! We've completely removed the time restrictions on the club. Drop in anytime, day or night, to chat, vibe, and mingle with zero restrictions.
                </div>
            </div>
        </div>

        <div style="display:flex;align-items:flex-start;gap:16px;margin-bottom:20px;background:#fdf4ff;border-radius:16px;padding:18px;border-left:4px solid #d946ef;">
            <div style="font-size:26px;flex-shrink:0;">🎯</div>
            <div>
                <div style="font-size:15px;font-weight:900;color:#86198f;margin-bottom:4px;">4. Stricter, Smarter Matchmaking</div>
                <div style="font-size:14px;color:#555;line-height:1.6;">
                    We've refined our AI matching! The system now strictly enforces opposite-gender filtering. Your Swipes and Dashboard matches are curated exclusively to show you exactly who you are looking for.
                </div>
            </div>
        </div>
    </div>

    <!-- HAPPY MATCHMAKING CTA -->
    <div style="margin:0 36px 36px;background:linear-gradient(135deg,#720000 0%,#E60026 100%);border-radius:20px;padding:30px 25px;text-align:center;">
        <div style="font-size:38px;margin-bottom:10px;">💖</div>
        <h3 style="color:white;font-size:20px;font-weight:900;margin:0 0 10px;letter-spacing:-0.3px;">Ready to see it in action?</h3>
        <p style="color:rgba(255,255,255,0.9);font-size:14px;line-height:1.6;margin:0 0 22px;">
            Jump back in, complete your profile, and let the AI find your perfect match.
        </p>
        <div style="display:flex; justify-content:center; gap:10px; flex-wrap:wrap;">
            <a href="{BASE_URL}/dashboard" style="display:inline-block;background:white;color:#720000;font-weight:900;font-size:14px;padding:14px 24px;border-radius:50px;text-decoration:none;box-shadow:0 8px 25px rgba(0,0,0,0.15);">
                &#128150; Open Dashboard
            </a>
            <a href="{BASE_URL}/swipe" style="display:inline-block;background:#333;color:white;font-weight:900;font-size:14px;padding:14px 24px;border-radius:50px;text-decoration:none;box-shadow:0 8px 25px rgba(0,0,0,0.15);">
                🔥 Start Swiping
            </a>
        </div>
    </div>

    <!-- FOOTER -->
    <div style="background:#fafafa;padding:24px 36px;text-align:center;border-top:1px solid #f0f0f0;">
        <p style="margin:0 0 6px;font-size:13px;font-weight:800;color:#555;text-transform:uppercase;letter-spacing:1px;">
            FIND YOUR MATCH AI &mdash; Kenya's Premier Campus Dating Platform
        </p>
        <p style="margin:0 0 6px;font-size:12px;color:#aaa;">Wishing you love, laughter, and the perfect match &#128140;</p>
        <p style="margin:0;font-size:11px;color:#ccc;">
            &copy; {YEAR} Delstarford Works. All rights reserved. &nbsp;|&nbsp;
            <a href="{BASE_URL}" style="color:#E60026;text-decoration:none;">findyourmatch.co.ke</a>
            &nbsp;|&nbsp; Reply UNSUBSCRIBE to opt out.
        </p>
    </div>

</div>
</body>
</html>"""

    msg = MIMEMultipart("mixed")
    msg["Subject"]    = subject
    msg["From"]       = formataddr(("FIND YOUR MATCH AI", MAIL_USERNAME))
    msg["To"]         = recipient_email
    msg["Date"]       = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="findyourmatch.co.ke")

    body = MIMEMultipart("alternative")
    body.attach(MIMEText(text_body, "plain", "utf-8"))
    body.attach(MIMEText(html_body,  "html",  "utf-8"))
    msg.attach(body)
    return msg


def open_smtp():
    """Opens a fresh SSL SMTP connection and returns the server object."""
    context = ssl._create_unverified_context()
    server  = smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT, context=context, timeout=30)
    server.login(MAIL_USERNAME, MAIL_PASSWORD)
    return server


# ── Load users ─────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("Loading user database from Firebase...")
try:
    from app.database import db
    all_data = db.reference("profiles").get() or {}
    users = [
        {**v, "id": k}
        for k, v in all_data.items()
        if isinstance(v, dict)
        and v.get("email")
        and not v.get("email_opt_out")
        and not v.get("is_banned")
    ]
    print(f"Found {len(users)} user(s) to notify (including unverified).\n")
except Exception as e:
    print(f"WARNING: Could not load Firebase users ({e}).")
    print("Falling back to a test send to the noreply address.\n")
    users = [{"name": "Test User", "email": MAIL_USERNAME}]

if not users:
    print("No eligible users found. Exiting.")
    sys.exit(0)

# ── Batched send ───────────────────────────────────────────────────────────────
print(f"{'#':<6} {'Name':<22} {'Email':<40} {'Status'}")
print("-" * 78)

sent   = 0
failed = 0
server = None

for i, user in enumerate(users, 1):
    name  = user.get("name", "Student").split()[0]
    email = user.get("email", "")

    # Open (or reopen) SMTP connection at the start of every batch
    if (i - 1) % BATCH_SIZE == 0:
        if server:
            try: server.quit()
            except: pass
        try:
            server = open_smtp()
            print(f"  [SMTP] Connected (batch starting at #{i})")
        except Exception as conn_err:
            print(f"  [SMTP] CONNECTION FAILED: {conn_err}")
            # Mark remaining users as failed
            for j, u in enumerate(users[i-1:], i):
                n = u.get("name","Student").split()[0]
                e = u.get("email","")
                print(f"{j:<6} {n:<22} {e:<40} FAILED: no SMTP connection")
                failed += 1
            break

    try:
        msg = build_email(name, email)
        server.send_message(msg)
        print(f"{i:<6} {name:<22} {email:<40} SENT")
        sent += 1
        time.sleep(0.3)   # polite 300ms delay between emails
    except Exception as e:
        print(f"{i:<6} {name:<22} {email:<40} FAILED: {e}")
        failed += 1
        # Force reconnect on next iteration
        try: server.quit()
        except: pass
        server = None

if server:
    try: server.quit()
    except: pass

print()
print("=" * 65)
print(f"  BROADCAST COMPLETE")
print(f"  Sent   : {sent}")
print(f"  Failed : {failed}")
print(f"  Total  : {sent + failed}")
print("=" * 65)
