"""
send_sponsor_match_email_job.py
===============================
Weekly job (e.g. Wednesday 10 AM) to send match emails to Sponsors.
Recommends eligible, verified students to sponsors.
"""

import os
import sys
import time
import random
import logging
import argparse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load env FIRST
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_sponsors, get_all_profiles, initialize_firebase
from email_service import _send_email
from firebase_admin import db as firebase_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("sponsor_mailer")

EAT = timezone(timedelta(hours=3))
EMAIL_DELAY_SECONDS = 2.0

def get_week_key():
    now = datetime.now(EAT)
    return now.strftime("%Y-W%W")

def get_sent_log():
    week_key = get_week_key()
    try:
        data = firebase_db.reference(f"email_logs/sponsor_weekly/{week_key}").get() or {}
        return set(data.keys())
    except:
        return set()

def mark_sent(user_id, email):
    week_key = get_week_key()
    try:
        firebase_db.reference(f"email_logs/sponsor_weekly/{week_key}/{user_id}").set({
            "email": email,
            "sent_at": datetime.now(EAT).isoformat()
        })
    except: pass

def build_html(name, students):
    base_url = os.getenv("BASE_URL", "https://findyourmatch.co.ke")
    cards = ""
    for s in students:
        cards += f"""
        <div style="display:inline-block;width:45%;margin:2%;background:#fff;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden;text-align:center;box-shadow:0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="height:140px;background:url('{s.get('photo_url') or s.get('img') or '/static/img/placeholder.png'}') center/cover;"></div>
            <div style="padding:15px;">
                <h4 style="margin:0;color:#0f172a;font-size:16px;font-weight:900;">{s.get('name', 'Student').split()[0]}, {s.get('age', '?')}</h4>
                <p style="margin:5px 0 0 0;color:#64748b;font-size:12px;">{s.get('institution', 'Campus')}</p>
                <a href="{base_url}/sponsor/login" style="display:inline-block;margin-top:10px;padding:6px 12px;background:#f5f3ff;color:#7c3aed;text-decoration:none;border-radius:6px;font-size:12px;font-weight:bold;border:1px solid #ddd6fe;">Connect</a>
            </div>
        </div>
        """

    return f"""<!DOCTYPE html>
    <html><body style="font-family:sans-serif;background:#f8fafc;padding:20px;margin:0;">
        <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;">
            <div style="background:linear-gradient(135deg,#720000,#e60026);padding:25px;text-align:center;color:white;">
                <h1 style="margin:0;font-size:24px;">FindYourMatch Sponsors</h1>
            </div>
            <div style="padding:30px;text-align:center;color:#334155;">
                <p>Hello {name},</p>
                <p>Here are some amazing students looking to connect with sponsors this week:</p>
                <div style="margin-top:20px;">{cards}</div>
                <div style="margin-top:30px;">
                    <a href="{base_url}/sponsor/login" style="display:inline-block;padding:14px 32px;background:#e60026;color:white;text-decoration:none;border-radius:30px;font-weight:bold;">Go to Dashboard</a>
                </div>
            </div>
        </div>
    </body></html>"""

def run(dry_run=False):
    logger.info("Starting Sponsor Weekly Emails")
    initialize_firebase()
    
    sponsors = get_all_sponsors(verified_only=True)
    students = [s for s in get_all_profiles() if s.get('is_verified') and not s.get('is_banned')]
    already_sent = get_sent_log()
    
    success = 0
    fail = 0
    
    for idx, sponsor in enumerate(sponsors, 1):
        email = sponsor.get("email", "").strip()
        name = sponsor.get("name", "Sponsor").split()[0]
        sid = sponsor.get("id")
        
        if sid in already_sent:
            continue
            
        # Basic matching (random sample for now, could be enhanced based on preferences)
        pool = random.sample(students, min(6, len(students)))
        if not pool:
            continue
            
        subject = "🌟 Your Top Student Matches This Week"
        html = build_html(name, pool)
        
        logger.info(f"[{idx}/{len(sponsors)}] Sending to {email}...")
        if not dry_run:
            try:
                if _send_email(email, subject, "Check out your matches!", html):
                    success += 1
                    mark_sent(sid, email)
                else:
                    fail += 1
            except Exception as e:
                logger.error(f"Error: {e}")
                fail += 1
            time.sleep(EMAIL_DELAY_SECONDS)
        else:
            success += 1
            
    logger.info(f"Done. Sent: {success}, Failed: {fail}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.dry_run)
