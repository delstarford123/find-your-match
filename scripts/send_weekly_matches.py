import os
import smtplib
import random
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH", "credentials.json"))
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.getenv("FIREBASE_DATABASE_URL", "https://mmust-dating-ai-default-rtdb.firebaseio.com/")
        })
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        exit(1)

# SMTP Config
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
        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, timeout=20)
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def get_html_template(title, message, profiles):
    # Professional Email Template
    profile_cards = ""
    for p in profiles:
        img_url = p.get('photo_url') or 'https://findyourmatch.co.ke/static/default_avatar.png'
        name = p.get('name', 'Someone')
        age = p.get('age', '?')
        institution = p.get('institution', 'Campus')
        
        profile_cards += f'''
        <div style="display: inline-block; width: 45%; margin: 2%; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            <div style="height: 120px; background: url('{img_url}') center/cover no-repeat; border-bottom: 2px solid #0ea5e9;"></div>
            <div style="padding: 15px;">
                <h4 style="margin: 0; color: #0f172a; font-size: 16px;">{name}, {age}</h4>
                <p style="margin: 5px 0 0 0; color: #64748b; font-size: 12px;">{institution}</p>
            </div>
        </div>
        '''

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Arial', sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }}
            .header {{ background: linear-gradient(135deg, #0284c7, #0ea5e9); padding: 30px; text-align: center; color: white; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: bold; letter-spacing: 1px; }}
            .content {{ padding: 30px; color: #334155; line-height: 1.6; text-align: center; }}
            .content h2 {{ color: #0f172a; margin-top: 0; }}
            .profiles-grid {{ text-align: center; margin-top: 20px; }}
            .btn {{ display: inline-block; padding: 14px 28px; background: #10b981; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; margin-top: 25px; }}
            .footer {{ background: #f1f5f9; padding: 20px; text-align: center; color: #94a3b8; font-size: 12px; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>FindYourMatch</h1>
            </div>
            <div class="content">
                <h2>{title}</h2>
                <p>{message}</p>
                
                <div class="profiles-grid">
                    {profile_cards}
                </div>
                
                <a href="https://findyourmatch.co.ke/login" class="btn">Log In to Message</a>
            </div>
            <div class="footer">
                &copy; {datetime.now().year} FindYourMatch.co.ke | Built for University Students<br>
                To stop receiving these alerts, update your settings in the app.
            </div>
        </div>
    </body>
    </html>
    """
    return html

def main():
    logger.info("Starting Weekly Matches Email Job...")
    
    # 1. Fetch all profiles
    profiles_ref = db.reference('profiles')
    all_profiles = profiles_ref.get() or {}
    
    if not all_profiles:
        logger.info("No profiles found in database.")
        return
        
    # Group active profiles by gender for fallback
    active_males = []
    active_females = []
    
    for uid, data in all_profiles.items():
        if data.get('email'):
            gender = str(data.get('gender', '')).lower()
            if gender == 'male' or gender == 'm':
                active_males.append((uid, data))
            elif gender == 'female' or gender == 'f':
                active_females.append((uid, data))
                
    sent_count = 0
    
    # 2. Loop through users and send emails
    for uid, user_data in all_profiles.items():
        email = user_data.get('email')
        if not email:
            continue
            
        likes_received = user_data.get('likes_received', {})
        likes_sent = user_data.get('likes_sent', {})
        
        # Find mutual matches
        mutual_uids = [pid for pid in likes_received if pid in likes_sent]
        
        # Find who they actually matched with (limit to 10 for email)
        match_profiles = []
        for match_uid in mutual_uids[:10]:
            if match_uid in all_profiles:
                match_profiles.append(all_profiles[match_uid])
                
        if match_profiles:
            # SEND MATCH EMAIL
            subject = f"You have {len(mutual_uids)} new matches waiting for you! 🔥"
            title = "It's a Match!"
            msg = "Great news! These students liked you back. Don't keep them waiting—log in and say hi."
            
            html = get_html_template(title, msg, match_profiles)
            if send_email(email, subject, html):
                sent_count += 1
                logger.info(f"Sent Matches to {email}")
                
        else:
            # SEND FALLBACK (10 Suggestions)
            pref_gender = str(user_data.get('gender_preference', '')).lower()
            pool = active_males if (pref_gender == 'male' or pref_gender == 'm') else active_females
            
            # If preference is 'both' or missing, mix them
            if not pool:
                pool = active_males + active_females
                
            # Filter out self
            pool = [p for p in pool if p[0] != uid]
            
            if not pool:
                continue
                
            # Pick up to 10 random profiles
            sampled = random.sample(pool, min(10, len(pool)))
            fallback_profiles = [p[1] for p in sampled]
            
            subject = "Check out these new profiles near you! ✨"
            title = "Potential Matches You Missed"
            msg = "You don't have any new mutual matches this week, but we found these active profiles at your campus that you might like. Swipe right!"
            
            html = get_html_template(title, msg, fallback_profiles)
            if send_email(email, subject, html):
                sent_count += 1
                logger.info(f"Sent Suggestions to {email}")
                
    logger.info(f"Finished. Sent {sent_count} weekly match emails.")

if __name__ == "__main__":
    import sys
    from datetime import datetime
    main()
