import os
import logging
import smtplib
import textwrap
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

logger = logging.getLogger(__name__)

def _send_email(recipient_email, subject, text_content, html_content, sender_name="MMUST AI Powered Dating "):
    """
    Private helper function to handle the actual SMTP connection and email dispatch.
    This prevents repeating connection and error-handling code for every email type.
    """
    sender_email = os.getenv("MAIL_USERNAME")
    sender_password = os.getenv("MAIL_PASSWORD")
    
    # Allows switching to SendGrid/AWS later via .env without changing code
    smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("MAIL_PORT", 465))

    if not sender_email or not sender_password:
        logger.error("Email credentials missing in environment variables!")
        return False

    # Create the multipart message container
    msg = MIMEMultipart("alternative")
    msg['Subject'] = subject
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = recipient_email

    # Attach parts (Attach TEXT first, then HTML so clients prefer HTML)
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        # Use context manager (with) to safely close connection even on failure
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
            
        logger.info(f"✅ Email '{subject}' sent to {recipient_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("❌ Email Auth Error: Check your SMTP App Password.")
        return False
    except Exception as e:
        logger.error(f"❌ Failed to send email to {recipient_email}: {e}")
        return False


def send_verification_email(recipient_email, user_name, otp_code):
    """Sends a formatted HTML verification email with a plain-text fallback."""
    subject = "Your MMUST AI Powered Dating Verification Code"
    
    # textwrap.dedent removes the ugly leading spaces caused by Python indentation
    text_content = textwrap.dedent(f"""\
        Welcome to the FYM, {user_name}!
        
        You are one step away from finding your perfect match at MMUST. 
        Please enter the verification code below to activate your account:
        
        {otp_code}
        
        If you did not sign up for this account, please ignore this email.
    """)

    html_content = textwrap.dedent(f"""\
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
    """)

    return _send_email(recipient_email, subject, text_content, html_content, sender_name="Delstarford Works")


def send_date_approval_email(to_email, user_name, partner_name, restaurant_name, date_day, date_time, location):
    """Sends a professional confirmation email to a student when a date is approved."""
    subject = f"Your Date at {restaurant_name} is Confirmed!"
    
    text_content = textwrap.dedent(f"""\
        Great news, {user_name}!
        
        Your upcoming date with {partner_name} has been officially approved by the management at {restaurant_name}.
        
        Reservation Details:
        When: {date_day} at {date_time}
        Where: {restaurant_name} ({location})
        
        A special table has been specifically reserved for you. When you arrive, simply open your MMUST Dating App and scan the merchant's QR code at the counter to verify your student status and claim your table!
        
        Have fun and stay safe!
        - The MMUST AI Powered Dating  Team
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #E60026; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                <h2 style="color: #720000; margin-top: 0; font-size: 24px; font-weight: 900;">Great news, {user_name}! 🎉</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    Your upcoming date with <strong>{partner_name}</strong> has been officially approved by the management at <strong>{restaurant_name}</strong>.
                </p>
                
                <div style="background: #FEF2F4; padding: 25px; border-radius: 12px; border: 1px solid #FFD6DD; margin: 25px 0;">
                    <h3 style="color: #E60026; margin-top: 0; margin-bottom: 15px; font-size: 18px; font-weight: 900;">Your Reservation Details</h3>
                    <p style="margin: 8px 0; color: #4A0008; font-size: 15px;"><strong>📅 When:</strong> {date_day} at {date_time}</p>
                    <p style="margin: 8px 0; color: #4A0008; font-size: 15px;"><strong>📍 Where:</strong> {restaurant_name} ({location})</p>
                </div>
                
                <p style="color: #555; font-size: 15px; line-height: 1.6;">
                    A special table has been specifically reserved for you. When you arrive, simply open your MMUST Dating App and scan the merchant's QR code at the counter to verify your student status and claim your table!
                </p>
                
                <p style="color: #888; font-size: 14px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 20px;">
                    Have fun and stay safe! <br>
                    <strong>- The MMUST AI Powered Dating  Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(to_email, subject, text_content, html_content)
def send_broadcast_email(recipient_email, recipient_name, subject, message_body):
    """Sends a generic mass broadcast email to users."""
    
    # Format line breaks in HTML
    html_message_body = message_body.replace('\n', '<br>')
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},
        
        {message_body}
        
        - The MMUST AI Powered Dating  Team
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #E60026; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                
                <h3 style="color: #720000; margin-top: 0; font-size: 20px; font-weight: 900;">Hello {recipient_name},</h3>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    {html_message_body}
                </p>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                    Best regards, <br>
                    <strong>The MMUST AI Powered Dating  Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)