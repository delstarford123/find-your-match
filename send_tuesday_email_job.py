"""
send_tuesday_email_job.py
=========================
Standalone cron script for Tuesday 09:00 EAT weekly match emails.

Uses the same database + email_service pattern as send_update_campaign.py
and send_apology_emails.py so SMTP is handled identically to the rest of the app.

Add this in cPanel Cron Jobs:
  Minute:  0
  Hour:    6
  Day:     *
  Month:   *
  Weekday: 2

  Command:
  /home/YOURUSERNAME/mmust-dating-ai/.venv/bin/python /home/YOURUSERNAME/mmust-dating-ai/send_tuesday_email_job.py >> /home/YOURUSERNAME/logs/tuesday_email.log 2>&1
"""

import os
import sys
import time
import random
import logging
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load env FIRST — exactly like send_update_campaign.py
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

# Now import app modules (they read env vars on import)
from database import get_all_profiles, initialize_firebase
from email_service import _send_email   # same private helper used by all email functions
from firebase_admin import db as firebase_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("tuesday_mailer")

EAT = timezone(timedelta(hours=3))

# Delay between sends (seconds) — same pattern as send_apology_emails.py
EMAIL_DELAY_SECONDS = 2.0

# ---------------------------------------------------------------------------
# Loving, blessed-day message pools — randomly rotated per send
# ---------------------------------------------------------------------------
MATCH_SUBJECTS = [
    "💖 Good morning, love! Your perfect match is waiting for you 🌟",
    "🌹 Have a blessed Tuesday — your perfect match found you! 💌",
    "✨ Sending you love today — your perfect match is right here 💕",
    "💌 You are loved! See who's waiting for you this Tuesday 🌸",
    "🌟 A blessed day to you! Your perfect match is just a click away 💖",
]

MATCH_MESSAGES = [
    (
        "Good morning, beautiful soul! ☀️ Wishing you the most wonderful and blessed Tuesday. "
        "You deserve every bit of love and happiness that comes your way. "
        "Your <strong>perfect match</strong> is right here, waiting to meet you — "
        "don't keep them waiting! Step into something beautiful today. 💖"
    ),
    (
        "Rise and shine! 🌟 May this Tuesday bring you joy, warmth, and countless blessings. "
        "We've handpicked the profiles that are most compatible with you, "
        "because <strong>your perfect match is out there</strong> — and they're closer than you think. "
        "Have a blessed and love-filled day! 🌹"
    ),
    (
        "Sending you love and light today! ✨ You are special, you are worthy, "
        "and someone incredible is looking for exactly who you are. "
        "Below are your <strong>top compatibility matches</strong> — "
        "take a moment, reach out, and let love unfold. Wishing you a beautiful, blessed Tuesday! 💕"
    ),
    (
        "Hello, wonderful you! 🌸 May your Tuesday be filled with sunshine, warm smiles, "
        "and the kind of love that takes your breath away. "
        "Your <strong>perfect match</strong> is waiting on the other side of a simple 'hello' — "
        "be brave, be you, and have a truly blessed day! 💌"
    ),
]

FALLBACK_SUBJECTS = [
    "🌸 Wishing you a blessed Tuesday — meet some amazing people today! 💖",
    "✨ Good morning! Discover wonderful people on FindYourMatch 🌟",
    "💌 A little love for your Tuesday — explore these amazing profiles! 🌹",
    "🌹 Someone wonderful is waiting for you — have a blessed day! ✨",
]

FALLBACK_MESSAGES = [
    (
        "Good morning, precious one! ☀️ Wishing you the most blessed Tuesday. "
        "Love has a beautiful way of showing up when you least expect it. "
        "Here are some wonderful, <strong>active profiles</strong> from your campus — "
        "take a look, reach out, and let today be the beginning of something magical. 💖"
    ),
    (
        "Rise and be blessed today! 🌟 We haven't found a perfect algorithmic match for you yet, "
        "but that doesn't mean love isn't right around the corner. "
        "Below are some <strong>amazing people</strong> on campus who could be just what you're looking for. "
        "Have the courage to say hello — your perfect match is waiting! 🌹"
    ),
    (
        "Hello, beautiful! ✨ May this Tuesday overflow with joy and blessings for you. "
        "We're still searching for your highest compatibility match, "
        "but in the meantime, meet these <strong>incredible people</strong> nearby — "
        "love doesn't always follow a formula, and that's the beauty of it. "
        "Wishing you a warm and love-filled day! 💕"
    ),
]


def build_profile_cards(profiles):
    """Build HTML profile cards for the email body."""
    cards = ""
    for p in profiles:
        img_url = p.get('photo_url') or 'https://findyourmatch.co.ke/static/default_avatar.png'
        name = p.get('name', 'Anonymous').split()[0]
        age = p.get('age', '?')
        institution = p.get('institution', 'Campus')
        compat = p.get('compatibility', None)

        compat_badge = (
            f'<div style="position: absolute; top: 10px; right: 10px; background: #e60026; '
            f'color: white; padding: 4px 8px; border-radius: 20px; font-size: 11px; '
            f'font-weight: bold;">{compat}% Match</div>'
        ) if compat else ''

        cards += f"""
        <div style="display: inline-block; width: 45%; margin: 2%; background: #ffffff;
                    border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden;
                    text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
                    position: relative;">
            {compat_badge}
            <div style="height: 140px; background: url('{img_url}') center/cover no-repeat;
                        border-bottom: 3px solid #e60026;"></div>
            <div style="padding: 15px;">
                <h4 style="margin: 0; color: #0f172a; font-size: 16px; font-weight: 900;">{name}, {age}</h4>
                <p style="margin: 5px 0 0 0; color: #64748b; font-size: 12px;">{institution}</p>
                <a href="https://findyourmatch.co.ke/student/{p.get('id', '')}"
                   style="display: inline-block; margin-top: 10px; padding: 6px 12px;
                          background: #fef2f2; color: #e60026; text-decoration: none;
                          border-radius: 6px; font-size: 12px; font-weight: bold;
                          border: 1px solid #fecaca;">View Profile</a>
            </div>
        </div>
        """
    return cards


def build_html(message, profile_cards):
    """Build the full HTML email body."""
    year = datetime.now(EAT).year
    base_url = os.getenv("BASE_URL", "https://findyourmatch.co.ke")
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: 'Arial', sans-serif; background-color: #f8fafc; margin: 0; padding: 20px;">
    <div style="max-width: 600px; margin: 0 auto; background: #ffffff;
                border-radius: 16px; overflow: hidden;
                box-shadow: 0 10px 25px rgba(0,0,0,0.05);">

        <!-- Header -->
        <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
            <img src="{base_url}/static/img/icon-512.png" alt="Find Your Match"
                 style="width: 100%; max-width: 220px; height: auto; display: block; margin: 0 auto;">
        </div>
        <div style="background: linear-gradient(135deg, #720000 0%, #e60026 100%);
                    padding: 25px; text-align: center; color: white;">
            <h1 style="margin: 0 0 6px 0; font-size: 24px; font-weight: 900; letter-spacing: 1px;">
                FindYourMatch
            </h1>
            <p style="margin: 0; font-size: 13px; opacity: 0.9;">💖 Connecting Hearts on Campus 💖</p>
        </div>

        <!-- Body -->
        <div style="padding: 30px; color: #334155; line-height: 1.6; text-align: center;">
            <p style="font-size: 15px;">{message}</p>

            <!-- Profile Cards -->
            <div style="text-align: center; margin-top: 20px;">
                {profile_cards}
            </div>

            <!-- CTA Button -->
            <div style="margin-top: 30px;">
                <a href="{base_url}/matches"
                   style="display: inline-block; padding: 14px 32px;
                          background: linear-gradient(135deg, #720000, #e60026);
                          color: white; text-decoration: none; border-radius: 30px;
                          font-size: 15px; font-weight: bold; letter-spacing: 0.5px;
                          box-shadow: 0 4px 15px rgba(230,0,38,0.3);">
                    💌 See All My Matches
                </a>
            </div>

            <!-- Blessing sign-off -->
            <p style="margin-top: 28px; font-size: 14px; color: #64748b; font-style: italic;">
                May today bring you joy, love, and every blessing you deserve. 🌟<br>
                Your perfect match is out there — and they are waiting for <em>you</em>. 💖
            </p>
        </div>

        <!-- Footer -->
        <div style="background: #f1f5f9; padding: 20px; text-align: center;
                    color: #94a3b8; font-size: 12px; border-top: 1px solid #e2e8f0;">
            &copy; {year} FindYourMatch.co.ke | Built for University Students<br>
            <a href="{base_url}/unsubscribe" style="color: #94a3b8; text-decoration: underline;">Unsubscribe</a>
        </div>
    </div>
</body>
</html>"""


def send_tuesday_match_email(to_email, recipient_name, subject, message, profiles):
    """Send a Tuesday match email using the app's shared _send_email helper."""
    profile_cards = build_profile_cards(profiles)
    html_content = build_html(message, profile_cards)
    text_content = (
        f"Good morning {recipient_name}!\n\n"
        f"Have a blessed Tuesday! Your perfect match is waiting for you on FindYourMatch.\n\n"
        f"Visit https://findyourmatch.co.ke/matches to see your top matches.\n\n"
        f"May today bring you joy, love, and every blessing you deserve.\n"
        f"— The FindYourMatch Team"
    )
    return _send_email(to_email, subject, text_content, html_content, sender_name="FindYourMatch")


def compute_compatibility(user, candidate):
    """Score two profiles for compatibility (0–100)."""
    if user.get("gender") and candidate.get("gender") and user["gender"] == candidate["gender"]:
        return 0
    if not candidate.get("is_verified"):
        return 0
    if candidate.get("is_shadowbanned") or candidate.get("is_locked") or candidate.get("is_banned"):
        return 0
    score = 50
    if user.get("religion") and user.get("religion") == candidate.get("religion"):
        score += 15
    try:
        age_gap = abs(int(user.get("age", 22)) - int(candidate.get("age", 22)))
        if age_gap <= 2:   score += 10
        elif age_gap <= 5: score += 5
        elif age_gap > 8:  score -= 10
    except (ValueError, TypeError):
        pass
    if (user.get("institution") and user.get("institution") == candidate.get("institution")
            and user.get("institution") != "Other"):
        score += 10
    stop = {"i","am","a","the","and","to","for","in","of","my","is","at","on","with",
            "student","mmust","like","love","looking","here"}
    my_w    = set(user.get("bio", "").lower().split()) - stop
    their_w = set(candidate.get("bio", "").lower().split()) - stop
    score  += min(len(my_w & their_w) * 3, 15)
    return min(score, 100)


# ---------------------------------------------------------------------------
# Deduplication helpers — prevent sending the same email twice in one week
# ---------------------------------------------------------------------------

def get_week_key():
    """Returns a string like '2026-W41' identifying the current ISO week."""
    now = datetime.now(EAT)
    return now.strftime("%Y-W%W")


def get_sent_log():
    """Fetch the set of user IDs already emailed this week from Firebase."""
    week_key = get_week_key()
    try:
        data = firebase_db.reference(f"email_logs/tuesday/{week_key}").get() or {}
        return set(data.keys())
    except Exception as e:
        logger.warning(f"Could not fetch sent log (will proceed carefully): {e}")
        return set()


def mark_sent(user_id, email):
    """Record that this user was emailed this week."""
    week_key = get_week_key()
    try:
        firebase_db.reference(f"email_logs/tuesday/{week_key}/{user_id}").set({
            "email": email,
            "sent_at": datetime.now(EAT).isoformat()
        })
    except Exception as e:
        logger.warning(f"Could not write sent log for {email}: {e}")


def run(dry_run=False):
    logger.info("=" * 62)
    logger.info("  FYM — Tuesday Blessed-Day Match Emails")
    if dry_run:
        logger.info("  *** DRY RUN — no emails will be sent ***")
    logger.info("=" * 62)

    # Use the app's shared Firebase init (reads FIREBASE_DB_URL from .env)
    initialize_firebase()
    logger.info("Fetching all user profiles from Firebase ...")
    all_profiles = get_all_profiles()

    if not all_profiles:
        logger.warning("No profiles found in the database. Exiting.")
        return

    logger.info(f"Total profiles: {len(all_profiles)}")

    # Filter eligible users (verified, has email, not banned, not opted out)
    seen_emails = set()
    eligible = []
    for p in all_profiles:
        if not isinstance(p, dict):
            continue
        email = p.get("email", "").strip().lower()
        if (not email or "@" not in email or email in seen_emails):
            continue
        if (not p.get("is_verified") or p.get("is_banned") or p.get("email_opt_out")):
            continue
        seen_emails.add(email)
        eligible.append(p)

    logger.info(f"Eligible users to email: {len(eligible)}")

    # Load already-sent log for this week to prevent duplicates
    week_key = get_week_key()
    logger.info(f"Loading sent-log for week {week_key} ...")
    already_sent_ids = get_sent_log()
    logger.info(f"Already sent this week: {len(already_sent_ids)} user(s) — will be skipped.")
    logger.info("-" * 62)

    # Pre-split pools for fallback
    active_males   = [p for p in eligible if str(p.get('gender', '')).lower() in ['male', 'm']]
    active_females = [p for p in eligible if str(p.get('gender', '')).lower() in ['female', 'f']]

    success_count = 0
    fail_count = 0

    for idx, user in enumerate(eligible, start=1):
        email      = user.get("email", "").strip()
        first_name = (user.get("name") or "Friend").split()[0]
        user_id    = user.get("id", email)  # fall back to email if no id

        # --- DEDUPLICATION GUARD: skip if already sent this week ---
        if user_id in already_sent_ids:
            logger.info(f"[{idx}/{len(eligible)}] SKIPPED (already sent this week) -> {email}")
            continue

        # 1. Compute compatibility matches
        scored = []
        for c in all_profiles:
            if c.get("id") == user.get("id"):
                continue
            compat = compute_compatibility(user, c)
            if compat >= 50:
                c_copy = dict(c)
                c_copy['compatibility'] = compat
                scored.append((compat, c_copy))

        scored.sort(key=lambda x: x[0], reverse=True)
        matches = [m[1] for m in scored[:10]]

        if matches:
            subject = random.choice(MATCH_SUBJECTS)
            message = random.choice(MATCH_MESSAGES)
            profiles_to_send = matches
        else:
            # Fallback: gender-preference pool
            pref = str(user.get('gender_preference', '')).lower()
            pool = active_males if pref in ['male', 'm'] else active_females
            if not pool:
                pool = active_males + active_females
            pool = [p for p in pool if p.get('id') != user.get('id')]
            if not pool:
                logger.warning(f"[{idx}/{len(eligible)}] NO POOL -> skipping {email}")
                fail_count += 1
                continue
            profiles_to_send = random.sample(pool, min(10, len(pool)))
            subject = random.choice(FALLBACK_SUBJECTS)
            message = random.choice(FALLBACK_MESSAGES)

        logger.info(f"[{idx}/{len(eligible)}] Sending to {first_name} <{email}> ({len(profiles_to_send)} profiles) ...")

        if dry_run:
            logger.info(f"  [DRY RUN] Would send: {subject}")
            success_count += 1
            continue

        # Retry logic — same as send_apology_emails.py
        max_retries = 3
        sent = False
        for attempt in range(max_retries):
            try:
                ok = send_tuesday_match_email(email, first_name, subject, message, profiles_to_send)
                if ok:
                    logger.info(f"  [SUCCESS] Sent to {email}")
                    success_count += 1
                    sent = True
                    if not dry_run:
                        mark_sent(user_id, email)  # record in Firebase to prevent re-send
                    break
                else:
                    logger.error(f"  [FAIL] send_tuesday_match_email returned False for {email}")
                    if attempt < max_retries - 1:
                        time.sleep(5)
            except Exception as e:
                logger.error(f"  [ERROR] {email}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"  [RETRY] Attempt {attempt + 1}/{max_retries} in 10s ...")
                    time.sleep(10)

        if not sent:
            fail_count += 1

        # Rate-limit pause between sends
        time.sleep(EMAIL_DELAY_SECONDS)

    logger.info("=" * 62)
    logger.info("  TUESDAY BROADCAST COMPLETE")
    logger.info(f"  Sent:   {success_count}")
    logger.info(f"  Failed: {fail_count}")
    logger.info("=" * 62)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send Tuesday Blessed-Day Match Emails")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
