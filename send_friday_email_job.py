"""
send_friday_email_job.py
========================
Standalone cron script for Friday 16:00 EAT weekly match emails.

Add this in cPanel Cron Jobs:
  Minute: 0
  Hour:   13
  Day:    *
  Month:  *
  Weekday: 5

  Command:
  /home/YOURUSERNAME/mmust-dating-ai/.venv/bin/python /home/YOURUSERNAME/mmust-dating-ai/send_friday_email_job.py >> /home/YOURUSERNAME/logs/friday_email.log 2>&1
"""

import os
import sys
import smtplib
import random
import logging
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
sys.path.insert(0, BASE_DIR)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))

import firebase_admin
from firebase_admin import credentials, db

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_key.json"))
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.getenv("FIREBASE_DATABASE_URL", "https://mmust-dating-ai-default-rtdb.firebaseio.com/")
        })
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        sys.exit(1)

SMTP_SERVER = os.getenv("MAIL_SERVER", "mail.findyourmatch.co.ke")
SMTP_PORT = int(os.getenv("MAIL_PORT", 465))
SMTP_USER = os.getenv("MAIL_USERNAME", "noreply@findyourmatch.co.ke")
SMTP_PASS = os.getenv("MAIL_PASSWORD", "Delstarford123")

def send_email(to_email, subject, html_body):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"FindYourMatch <{SMTP_USER}>"
        msg['To'] = to_email
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def get_html_template(title, message, profiles):
    profile_cards = ""
    for p in profiles:
        img_url = p.get('photo_url') or 'https://findyourmatch.co.ke/static/default_avatar.png'
        name = p.get('name', 'Anonymous').split()[0]
        age = p.get('age', '?')
        institution = p.get('institution', 'Campus')
        compat = p.get('compatibility', None)
        
        compat_badge = f'<div style="position: absolute; top: 10px; right: 10px; background: #e60026; color: white; padding: 4px 8px; border-radius: 20px; font-size: 11px; font-weight: bold;">{compat}% Match</div>' if compat else ''
        
        profile_cards += f"""
        <div style="display: inline-block; width: 45%; margin: 2%; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); position: relative;">
            {compat_badge}
            <div style="height: 140px; background: url('{img_url}') center/cover no-repeat; border-bottom: 3px solid #e60026;"></div>
            <div style="padding: 15px;">
                <h4 style="margin: 0; color: #0f172a; font-size: 16px; font-weight: 900;">{name}, {age}</h4>
                <p style="margin: 5px 0 0 0; color: #64748b; font-size: 12px;">{institution}</p>
                <a href="https://findyourmatch.co.ke/student/{p.get('id', '')}" style="display: inline-block; margin-top: 10px; padding: 6px 12px; background: #fef2f2; color: #e60026; text-decoration: none; border-radius: 6px; font-size: 12px; font-weight: bold; border: 1px solid #fecaca;">View Profile</a>
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="font-family: 'Arial', sans-serif; background-color: #f8fafc; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <div style="background: linear-gradient(135deg, #720000 0%, #e60026 100%); padding: 30px; text-align: center; color: white;">
                <h1 style="margin: 0; font-size: 26px; font-weight: 900; letter-spacing: 1px;">FindYourMatch</h1>
            </div>
            <div style="padding: 30px; color: #334155; line-height: 1.6; text-align: center;">
                <h2 style="color: #0f172a; margin-top: 0; font-size: 22px;">{title}</h2>
                <p style="font-size: 15px;">{message}</p>
                
                <div style="text-align: center; margin-top: 20px;">
                    {profile_cards}
                </div>
            </div>
            <div style="background: #f1f5f9; padding: 20px; text-align: center; color: #94a3b8; font-size: 12px; border-top: 1px solid #e2e8f0;">
                &copy; {datetime.now(EAT).year} FindYourMatch.co.ke | Built for University Students<br>
            </div>
        </div>
    </body>
    </html>
    """
    return html

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

def main():
    logger.info("=" * 55)
    logger.info(f"Friday Job Started")
    logger.info("=" * 55)

    all_data = db.reference("profiles").get() or {}
    all_profiles = [{**v, "id": k} for k, v in all_data.items() if isinstance(v, dict)]
    eligible = [u for u in all_profiles if u.get("is_verified") and u.get("email") and not u.get("email_opt_out") and not u.get("is_banned")]

    active_males = []
    active_females = []
    for p in eligible:
        gender = str(p.get('gender', '')).lower()
        if gender in ['male', 'm']:
            active_males.append(p)
        elif gender in ['female', 'f']:
            active_females.append(p)

    sent = 0
    skipped = 0

    for user in eligible:
        # 1. Compute Matches
        scored = []
        for c in all_profiles:
            if c.get("id") == user.get("id"):
                continue
            compat = compute_compatibility(user, c)
            if compat >= 50:
                c_copy = c.copy()
                c_copy['compatibility'] = compat
                scored.append((compat, c_copy))
                
        scored.sort(key=lambda x: x[0], reverse=True)
        matches = [m[1] for m in scored[:50]]

        if matches:
            subject = f"💌 Friday Perfect Matches: You have {len(matches)} perfect matches waiting!"
            html = get_html_template("It's a Match!", "It's Friday! The FYM weekend matchmaker has compiled your compatibility reports. Below are your top perfect matches on campus. Make your move before Lights Out!", matches)
            if send_email(user["email"], subject, html):
                sent += 1
                logger.info(f"  SENT MATCHES -> {user['email']}")
            else:
                skipped += 1
        else:
            # 2. Fallback logic
            pref_gender = str(user.get('gender_preference', '')).lower()
            pool = active_males if (pref_gender in ['male', 'm']) else active_females
            if not pool: pool = active_males + active_females
            
            pool = [p for p in pool if p['id'] != user.get('id')]
            
            if pool:
                fallback = random.sample(pool, min(10, len(pool)))
                subject = f"✨ Friday Perfect Matches: Check out these active profiles!"
                html = get_html_template("Suggested Profiles", "You don't have any perfect matches >50% right now, but we found these active profiles at your campus to check out before the weekend. Swipe right!", fallback)
                if send_email(user["email"], subject, html):
                    sent += 1
                    logger.info(f"  SENT FALLBACK -> {user['email']}")
                else:
                    skipped += 1
            else:
                skipped += 1

    logger.info(f"DONE | Sent: {sent} | Skipped: {skipped}")

if __name__ == "__main__":
    main()
