import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime
import json

# Setup environment variables (adjust paths for cPanel environment)
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), '..', 'admin_sdk.json')
# Ensure you update these with real SMTP credentials in your production environment
SMTP_SERVER = os.getenv('SMTP_SERVER', 'mail.hostpinnacle.co.ke')
SMTP_PORT = int(os.getenv('SMTP_PORT', 465))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', 'admin@yourdomain.com') # Replace with actual
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', 'yourpassword') # Replace with actual

def initialize_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(CREDENTIALS_PATH)
        # Remember to update the databaseURL below with your actual Firebase URL
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://find-your-match-36109-default-rtdb.firebaseio.com' 
        })

def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_USERNAME
        msg['To'] = to_email

        part = MIMEText(body, 'html')
        msg.attach(part)

        # Assuming SSL for Port 465
        server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, to_email, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

def generate_report():
    initialize_firebase()
    
    # 1. Fetch Campus Managers
    managers_ref = db.reference('campus_managers')
    managers = managers_ref.get()
    
    if not managers:
        print("No campus managers found.")
        return

    # 2. Fetch all profiles to calculate metrics per institution
    profiles_ref = db.reference('profiles')
    profiles = profiles_ref.get() or {}

    # Calculate subscribers (paid users) per institution
    institution_stats = {}
    for uid, profile in profiles.items():
        inst = profile.get('institution', 'Other')
        is_paid = profile.get('is_paid', False)
        
        if inst not in institution_stats:
            institution_stats[inst] = {'total_users': 0, 'paid_users': 0, 'revenue': 0}
            
        institution_stats[inst]['total_users'] += 1
        if is_paid:
            institution_stats[inst]['paid_users'] += 1
            institution_stats[inst]['revenue'] += 50 # 50 KSH per sub

    # 3. Send emails
    current_month = datetime.now().strftime('%B %Y')

    for manager_id, manager_data in managers.items():
        email = manager_data.get('email')
        name = manager_data.get('name')
        inst = manager_data.get('institution')
        
        if not email or not inst:
            continue

        stats = institution_stats.get(inst, {'total_users': 0, 'paid_users': 0, 'revenue': 0})
        paid_users = stats['paid_users']
        total_revenue = stats['revenue']
        commission = total_revenue * 0.30

        # Build email HTML
        html_body = f"""
        <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                    <div style="background-color: #E60026; color: white; padding: 20px; text-align: center;">
                        <h2 style="margin: 0;">Campus Manager Monthly Report</h2>
                        <p style="margin: 5px 0 0 0;">{current_month}</p>
                    </div>
                    <div style="padding: 20px;">
                        <p>Hi <strong>{name}</strong>,</p>
                        <p>Here is your performance report for <strong>{inst}</strong> this month.</p>
                        
                        <div style="background-color: #f9f9f9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                            <h3 style="margin-top: 0; color: #E60026;">Institution Stats</h3>
                            <ul style="list-style-type: none; padding-left: 0;">
                                <li style="margin-bottom: 10px;">📊 <strong>Total Registered Users:</strong> {stats['total_users']}</li>
                                <li style="margin-bottom: 10px;">💎 <strong>Premium Subscribers:</strong> {paid_users}</li>
                                <li style="margin-bottom: 10px;">💰 <strong>Estimated Revenue:</strong> KSH {total_revenue:,.2f}</li>
                            </ul>
                        </div>
                        
                        <div style="background-color: #e6f7ff; border-left: 4px solid #1890ff; padding: 15px; margin-bottom: 20px;">
                            <h3 style="margin-top: 0; color: #1890ff;">Your Commission (30%)</h3>
                            <p style="font-size: 24px; font-weight: bold; margin: 10px 0;">KSH {commission:,.2f}</p>
                            <p style="font-size: 12px; color: #666; margin: 0;">This amount is calculated based on the total premium subscribers from your institution.</p>
                        </div>
                        
                        <p>Keep up the great work promoting the network!</p>
                        <p>Best Regards,<br><strong>Find Your Match Admin Team</strong></p>
                    </div>
                </div>
            </body>
        </html>
        """

        send_email(email, f"Campus Manager Report - {current_month}", html_body)

if __name__ == "__main__":
    print(f"Starting Campus Manager Report Job at {datetime.now()}")
    generate_report()
    print("Job Completed.")
