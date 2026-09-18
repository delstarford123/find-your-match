"""
send_friday_email_job.py
========================
Standalone cron script for Friday 16:00 EAT weekly match emails.

Add this in cPanel Cron Jobs:
  Minute:  0
  Hour:    13         (13:00 UTC = 16:00 EAT)
  Day:     *
  Month:   *
  Weekday: 5          (5 = Friday)

  Command:
  /home/YOURUSERNAME/mmust-dating-ai/.venv/bin/python /home/YOURUSERNAME/mmust-dating-ai/send_friday_email_job.py >> /home/YOURUSERNAME/logs/friday_email.log 2>&1
"""

import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [FRIDAY-JOB] %(levelname)s: %(message)s"
)
logger = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))

logger.info("=" * 55)
logger.info("Friday Perfect Match Sheet Job Started")
logger.info(f"Time (EAT): {datetime.now(EAT).strftime('%Y-%m-%d %H:%M:%S')}")
logger.info("=" * 55)


def compute_compatibility(user, candidate):
    if user.get("gender") and candidate.get("gender") and user["gender"] == candidate["gender"]:
        return 0
    if not candidate.get("is_verified"):
        return 0
    if candidate.get("is_shadowbanned") or candidate.get("is_locked") or candidate.get("is_banned"):
        return 0
    score = 50
    if user.get("religion") and user.get("religion") == candidate.get("religion"):
        score += 15
    age_gap = abs(int(user.get("age", 22)) - int(candidate.get("age", 22)))
    if age_gap <= 2:   score += 10
    elif age_gap <= 5: score += 5
    elif age_gap > 8:  score -= 10
    if user.get("institution") and user.get("institution") == candidate.get("institution") and user.get("institution") != "Other":
        score += 10
    stop = {"i","am","a","the","and","to","for","in","of","my","is","at","on","with","student","mmust","like","love","looking","here"}
    my_w    = set(user.get("bio","").lower().split()) - stop
    their_w = set(candidate.get("bio","").lower().split()) - stop
    score  += min(len(my_w & their_w) * 3, 15)
    return min(score, 100)


def get_matches(user, all_profiles, limit=10):
    scored = []
    for c in all_profiles:
        if c.get("id") == user.get("id"):
            continue
        compat = compute_compatibility(user, c)
        if compat >= 50:
            scored.append((compat, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id":          c.get("id",""),
            "name":        c.get("name","Anonymous"),
            "course":      c.get("course") or c.get("reg_number","Student"),
            "institution": c.get("institution","Campus"),
            "bio":         (c.get("bio") or "No bio yet.")[:150],
            "phone":       c.get("phone","N/A"),
            "email":       c.get("email","N/A"),
            "zodiac":      c.get("zodiac",""),
            "mbti":        c.get("mbti",""),
            "compatibility": compat,
        }
        for compat, c in scored[:limit]
    ]


try:
    from app.database import db
    from app.email_service import send_friday_matches_email

    all_data = db.reference("profiles").get() or {}
    all_profiles = [{**v, "id": k} for k, v in all_data.items() if isinstance(v, dict)]
    eligible     = [u for u in all_profiles if u.get("is_verified") and u.get("email") and not u.get("email_opt_out") and not u.get("is_banned")]

    logger.info(f"Total profiles: {len(all_profiles)} | Eligible to email: {len(eligible)}")

    sent    = 0
    skipped = 0

    for user in eligible:
        matches = get_matches(user, all_profiles)
        if not matches:
            skipped += 1
            continue
        try:
            ok = send_friday_matches_email(
                recipient_email=user["email"],
                recipient_name=user.get("name","Student").split()[0],
                perfect_matches=matches
            )
            if ok:
                sent += 1
                logger.info(f"  SENT -> {user['email']}")
            else:
                skipped += 1
                logger.warning(f"  FAIL -> {user['email']}")
        except Exception as e:
            skipped += 1
            logger.error(f"  ERROR -> {user.get('email')}: {e}")

    logger.info(f"DONE | Sent: {sent} | Skipped: {skipped}")

except Exception as e:
    logger.error(f"Job crashed: {e}", exc_info=True)
    sys.exit(1)
