import os
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

logger = logging.getLogger(__name__)

def send_verification_email(recipient_email, user_name, otp_code):
    """
    Sends a beautifully formatted HTML verification email with a plain-text fallback.
    Returns True if successful, False otherwise.
    """
    sender_email = os.getenv("MAIL_USERNAME")
    sender_password = os.getenv("MAIL_PASSWORD")

    if not sender_email or not sender_password:
        logger.error("Email credentials missing in environment variables!")
        return False

    # Create the multipart message container
    msg = MIMEMultipart("alternative")
    msg['Subject'] = "Your MMUST AI Dating Verification Code"
    
    # PROPER WAY TO SET SENDER NAME (Prevents spam flagging)
    msg['From'] = formataddr(('Delstarford Works', sender_email))
    msg['To'] = recipient_email

    # 1. Plain Text Fallback (For simple email clients or accessibility)
    text_content = f"""
    Welcome to the Club, {user_name}!
    
    You are one step away from finding your perfect match at MMUST. 
    Please enter the verification code below to activate your account:
    
    {otp_code}
    
    If you did not sign up for this account, please ignore this email.
    """

    # 2. Beautiful Startup-Style HTML Version
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <div style="max-width: 600px; margin: 0 auto; background: white; border: 1px solid #FFD6DD; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(114,0,0,0.05);">
            
            <div style="background: linear-gradient(135deg, #720000 0%, #E60026 100%); padding: 35px 20px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: -0.5px;">
                    Welcome and Find Your Match, {user_name}! ✨
                </h1>
            </div>
            
            <div style="padding: 40px 30px; text-align: center;">
                <p style="font-size: 16px; color: #4A0008; line-height: 1.6; margin-top: 0;">
                    You are one step away from finding your perfect match at MMUST. Please enter the verification code below to activate your account:
                </p>
                
                <div style="font-size: 36px; font-weight: 900; color: #720000; letter-spacing: 8px; background: #FEF2F4; padding: 20px; border-radius: 12px; border: 2px dashed #E60026; margin: 35px auto; width: fit-content;">
                    {otp_code}
                </div>
                
                <p style="font-size: 13px; color: #888; margin-bottom: 0;">
                    If you did not sign up for this account, please ignore this email.
                </p>
            </div>
            
            <div style="background: #fafafa; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                <p style="margin: 0; font-size: 12px; color: #aaa; font-weight: bold;">
                    Powered by Delstarford Works
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    # Attach parts (Attach TEXT first, then HTML so clients prefer HTML)
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Use context manager (with) to safely close connection even on failure
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info(f"✅ Verification email sent to {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("❌ Email Auth Error: Check your Gmail App Password.")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to send email to {recipient_email}: {e}")
        return False