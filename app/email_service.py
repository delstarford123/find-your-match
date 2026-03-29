import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_verification_email(recipient_email, user_name, otp_code):
    sender_email = os.getenv("MAIL_USERNAME")
    sender_password = os.getenv("MAIL_PASSWORD")

    if not sender_email or not sender_password:
        print("❌ Email credentials missing in .env!")
        return False

    msg = MIMEMultipart("alternative")
    msg['Subject'] = "Your MMUST AI Dating Verification Code"
    msg['From'] = f"FIND YOUR MATCH <{sender_email}>"
    msg['To'] = recipient_email

    # Beautiful Startup-Style Email HTML
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #ffccd5; border-radius: 15px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #800000 0%, #ff2a4b 100%); padding: 30px; text-align: center;">
            <h1 style="color: white; margin: 0;">Welcome to the Club, {user_name}! ✨</h1>
        </div>
        <div style="padding: 30px; background: #fafafa; text-align: center;">
            <p style="font-size: 16px; color: #555;">You are one step away from finding your perfect match at MMUST. Please enter the verification code below to activate your account:</p>
            <div style="font-size: 32px; font-weight: bold; color: #800000; letter-spacing: 5px; background: white; padding: 15px; border-radius: 10px; border: 2px dashed #ff2a4b; margin: 30px auto; width: fit-content;">
                {otp_code}
            </div>
            <p style="font-size: 14px; color: #888;">If you did not sign up for this account, please ignore this email.</p>
        </div>
    </div>
    """
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Connect to Gmail's secure SMTP server
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, recipient_email, msg.as_string())
        server.quit()
        print(f"✅ Verification email sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False