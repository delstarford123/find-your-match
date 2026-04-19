import os
import logging
import smtplib
import textwrap
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

logger = logging.getLogger(__name__)

# Define standard sender name for consistency
SENDER_NAME_DEFAULT = "MMUST AI Powered Dating"

def _send_email(recipient_email, subject, text_content, html_content, sender_name=SENDER_NAME_DEFAULT):
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
    # CRITICAL FIX: Explicitly set 'utf-8' so emojis 🚀❤️ don't crash the server
    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

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
    
    text_content = textwrap.dedent(f"""\
        Welcome to FYM, {user_name}!
        
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
                        Welcome to FYM, {user_name}! ✨
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
        - {SENDER_NAME_DEFAULT} Team
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
                    <strong>- The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(to_email, subject, text_content, html_content)


def send_broadcast_email(recipient_email, recipient_name, subject, message_body):
    """Sends a generic mass broadcast email to users, generated by the Admin."""
    
    # Format line breaks in HTML so admin paragraphs render perfectly
    html_message_body = message_body.replace('\n', '<br>')
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},
        
        {message_body}
        
        - The {SENDER_NAME_DEFAULT} Team
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #38bdf8; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                
                <h3 style="color: #0f172a; margin-top: 0; font-size: 20px; font-weight: 900;">Hello {recipient_name},</h3>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    {html_message_body}
                </p>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                    Best regards, <br>
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_premium_activation_email(recipient_email, recipient_name):
    """Sends an email when a user successfully pays or activates a Premium promo."""
    subject = "💎 Your Premium Account is Active!"
    
    text_content = textwrap.dedent(f"""\
        Congratulations {recipient_name},
        
        Your Premium Subscription is now active! You now have full access to:
        - Unlimited Swiping
        - Voice & Video WebRTC Calling
        - The AI Wingman Assistant
        - Date Bookings at Partner Restaurants
        
        Log in now to see your new matches.
        
        - The {SENDER_NAME_DEFAULT} Team
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #10b981; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="font-size: 40px;">💎</span>
                </div>
                
                <h3 style="color: #0f172a; margin-top: 0; font-size: 24px; font-weight: 900; text-align: center;">Welcome to Premium, {recipient_name}!</h3>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6; text-align: center;">
                    Your account has been successfully upgraded. You now have unrestricted access to all features.
                </p>
                
                <ul style="color: #4A0008; font-size: 15px; line-height: 1.8; background: #f0fdf4; padding: 20px 20px 20px 40px; border-radius: 12px; border: 1px solid #bbf7d0;">
                    <li><strong>Unlimited Swiping</strong> (Find your perfect match)</li>
                    <li><strong>Live Voice & Video Calls</strong> (Connect instantly)</li>
                    <li><strong>AI Wingman</strong> (Never run out of things to say)</li>
                    <li><strong>Book Real Dates</strong> (Exclusive restaurant reservations)</li>
                </ul>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_admin_alert_email(recipient_email, recipient_name, action_type, reason):
    """Sends moderation emails (Warnings or Account Bans) from the Admin Dashboard."""
    
    if action_type == 'ban':
        subject = "🚫 Account Terminated: Violation of Terms"
        header_color = "#ef4444" # Red
        title = "Account Terminated"
        message = f"Your account has been permanently removed from the platform for the following reason:<br><br><strong>{reason}</strong>"
    else:
        subject = "⚠️ Official Warning from FYM Moderation"
        header_color = "#f59e0b" # Yellow
        title = "Official Warning"
        message = f"Your account has been flagged by our AI moderation system for the following reason:<br><br><strong>{reason}</strong><br><br>Please ensure your behavior aligns with our community guidelines to avoid a permanent ban."

    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},
        
        {title}
        Reason: {reason}
        
        - FYM Trust & Safety Team
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid {header_color}; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                
                <h3 style="color: {header_color}; margin-top: 0; font-size: 20px; font-weight: 900;">{title}</h3>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6; background: #f8fafc; padding: 15px; border-radius: 8px; border-left: 4px solid {header_color};">
                    {message}
                </p>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                    This is an automated message. <br>
                    <strong>FYM Trust & Safety Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)