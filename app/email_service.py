import os
import logging
import smtplib
import textwrap
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr

logger = logging.getLogger(__name__)

# Define standard sender name for consistency
SENDER_NAME_DEFAULT = "FIND YOUR MATCH AI"

def _send_email(recipient_email, subject, text_content, html_content, sender_name=SENDER_NAME_DEFAULT, attachments=None):
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

    # Create the mixed message container for attachments
    msg = MIMEMultipart("mixed")
    msg['Subject'] = subject
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = recipient_email

    # Create the multipart message container for body
    msg_body = MIMEMultipart("alternative")
    # Attach parts (Attach TEXT first, then HTML so clients prefer HTML)
    # CRITICAL FIX: Explicitly set 'utf-8' so emojis 🚀❤️ don't crash the server
    msg_body.attach(MIMEText(text_content, "plain", "utf-8"))
    msg_body.attach(MIMEText(html_content, "html", "utf-8"))
    msg.attach(msg_body)

    # Handle Attachments
    if attachments:
        for attachment in attachments:
            try:
                part = MIMEBase('application', "octet-stream")
                part.set_payload(attachment['content'])
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="{attachment["filename"]}"')
                msg.attach(part)
            except Exception as e:
                logger.error(f"Failed to attach file {attachment.get('filename')}: {e}")

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


def send_verification_email(recipient_email, user_name, otp_code, purpose="signup"):
    """
    Sends a formatted HTML verification email with a context-aware message.
    Purposes: 'signup', 'reset', 'resend'
    """
    if purpose == "reset":
        subject = "Reset Your FIND YOUR MATCH Password"
        headline = "Password Reset Request 🔑"
        message = "We received a request to reset your password. Use the code below to securely update your credentials. This code will expire soon."
    elif purpose == "resend":
        subject = "Your New Verification Code - FIND YOUR MATCH"
        headline = "New Verification Code 📩"
        message = "You requested a new verification code. Please enter the 6-digit code below to activate your account and start matching!"
    else:
        subject = "Welcome to FIND YOUR MATCH - Verify Your Email"
        headline = f"Welcome to FYM, {user_name}! ✨"
        message = "You are one step away from finding your perfect match. Please enter the verification code below to activate your account."
    
    text_content = textwrap.dedent(f"""\
        {headline}
        
        {message}
        
        Verification Code: {otp_code}
        
        If you did not request this, please ignore this email.
        
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
            <div style="max-width: 600px; margin: 0 auto; background: white; border: 1px solid #FFD6DD; border-radius: 24px; overflow: hidden; box-shadow: 0 15px 35px rgba(114,0,0,0.08);">
                
                <div style="background: linear-gradient(135deg, #720000 0%, #E60026 100%); padding: 45px 20px; text-align: center;">
                    <div style="background: rgba(255,255,255,0.2); width: 60px; height: 60px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px;">
                        <span style="font-size: 30px;">🔥</span>
                    </div>
                    <h1 style="color: white; margin: 0; font-size: 26px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.2;">
                        {headline}
                    </h1>
                </div>
                
                <div style="padding: 40px 35px; text-align: center;">
                    <p style="font-size: 17px; color: #4A0008; line-height: 1.6; margin-top: 0; font-weight: 500;">
                        {message}
                    </p>
                    
                    <div style="font-size: 42px; font-weight: 900; color: #720000; letter-spacing: 10px; background: #FEF2F4; padding: 25px 30px; border-radius: 16px; border: 2px dashed #E60026; margin: 35px auto; width: fit-content; display: inline-block;">
                        {otp_code}
                    </div>
                    
                    <p style="font-size: 14px; color: #888; margin-top: 30px; line-height: 1.5;">
                        If you did not request this code, you can safely ignore this email. Someone may have entered your email address by mistake.
                    </p>
                </div>
                
                <div style="background: #fafafa; padding: 30px; text-align: center; border-top: 1px solid #eee;">
                    <p style="margin: 0 0 10px; font-size: 12px; color: #aaa; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">
                        FIND YOUR MATCH AI Powered Dating
                    </p>
                    <p style="margin: 0; font-size: 11px; color: #ccc;">
                        &copy; {datetime.now().year} Delstarford Works. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content, sender_name=SENDER_NAME_DEFAULT)


def send_date_approval_email(to_email, user_name, partner_name, restaurant_name, date_day, date_time, location):
    """Sends a professional confirmation email to a student when a date is approved."""
    subject = f"Your Date at {restaurant_name} is Confirmed!"
    
    text_content = textwrap.dedent(f"""\
        Great news, {user_name}!
        
        Your upcoming date with {partner_name} has been officially approved by the management at {restaurant_name}.
        
        Reservation Details:
        When: {date_day} at {date_time}
        Where: {restaurant_name} ({location})
        
        A special table has been specifically reserved for you. When you arrive, simply open your FIND YOUR MATCH App and scan the merchant's QR code at the counter to verify your status and claim your table!
        
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
                    A special table has been specifically reserved for you. When you arrive, simply open your FIND YOUR MATCH App and scan the merchant's QR code at the counter to verify your status and claim your table!
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


def send_date_request_to_merchant_email(merchant_email, merchant_name, user_a_name, user_b_name, date_day, date_time):
    """Sends a notification email to a merchant when a new date is proposed at their venue."""
    subject = f"New Date Proposal: {user_a_name} & {user_b_name}"
    
    text_content = textwrap.dedent(f"""\
        Hello {merchant_name},
        
        A new date has been proposed at your venue!
        
        Couple: {user_a_name} & {user_b_name}
        Proposed Time: {date_day} at {date_time}
        
        Please log in to your Merchant Dashboard to approve or decline this reservation.
        
        - FIND YOUR MATCH AI Team
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #720000; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                <h2 style="color: #720000; margin-top: 0; font-size: 22px; font-weight: 900;">New Date Proposal! 🍽️</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    Hello <strong>{merchant_name}</strong>, a new couple wants to meet at your venue.
                </p>
                
                <div style="background: #fafafa; padding: 20px; border-radius: 12px; border: 1px solid #eee; margin: 25px 0;">
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>Couple:</strong> {user_a_name} & {user_b_name}</p>
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>Proposed Time:</strong> {date_day} at {date_time}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
    <a href="{{ url_for('business_login', _external=True) }}" style="background: #720000; color: white; padding: 14px 25px; text-decoration: none; border-radius: 8px; font-weight: 900; display: inline-block;">
        Open Merchant Dashboard
    </a>
</div>
                
                <p style="color: #888; font-size: 13px; margin-top: 30px; text-align: center;">
                    Manage your bookings and grow your business with FIND YOUR MATCH.
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(merchant_email, subject, text_content, html_content)


def send_broadcast_email(recipient_email, recipient_name, subject, message_body, attachments=None):
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

    return _send_email(recipient_email, subject, text_content, html_content, attachments=attachments)


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


def send_sos_admin_alert(user_name, user_id, user_phone, latitude, longitude, latest_date_info, alert_id):
    """Sends an high-priority emergency alert email to the super admin."""
    recipient_email = "delstarfordworks@gmail.com"
    subject = f"🚨 URGENT: SOS EMERGENCY ALERT - {user_name}"
    
    # Standalone Alert Page Link
    # Note: Replace with actual domain in production
    base_url = os.getenv("BASE_URL", "https://match-ai.onrender.com")
    alert_page_url = f"{base_url}/emergency/{alert_id}"
    
    map_link = f"https://www.google.com/maps?q={latitude},{longitude}" if latitude else "Location not shared"
    
    date_context = "No recent verified dates found."
    if latest_date_info:
        date_context = f"Latest Verified Date: {latest_date_info['partner_name']} at {latest_date_info['venue_name']} (Scanned at: {latest_date_info['scan_time']})"

    text_content = textwrap.dedent(f"""\
        🚨 EMERGENCY SOS ALERT 🚨
        
        User: {user_name} (ID: {user_id})
        Phone: {user_phone}
        
        LIVE MONITORING PAGE: {alert_page_url}
        
        Location: {map_link}
        
        Date Context:
        {date_context}
        
        IMMEDIATE ACTION REQUIRED.
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 20px; background-color: #720000; font-family: sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; overflow: hidden; border: 5px solid #E60026;">
                <div style="background: #E60026; padding: 30px; text-align: center; color: white;">
                    <h1 style="margin: 0; font-size: 32px; letter-spacing: 2px;">🚨 SOS ALERT 🚨</h1>
                </div>
                <div style="padding: 30px;">
                    <h2 style="color: #111; margin-top: 0;">{user_name} is in danger!</h2>
                    
                    <div style="text-align: center; margin: 20px 0;">
                        <a href="{alert_page_url}" style="background: #E60026; color: white; padding: 18px 30px; text-decoration: none; border-radius: 50px; font-weight: 900; font-size: 18px; display: inline-block; box-shadow: 0 10px 30px rgba(230,0,38,0.4);">
                            🔍 VIEW LIVE MONITORING PAGE
                        </a>
                    </div>

                    <p style="font-size: 16px; color: #333;"><strong>Student ID:</strong> {user_id}</p>
                    <p style="font-size: 16px; color: #333;"><strong>Phone:</strong> <a href="tel:{user_phone}">+{user_phone}</a></p>
                    
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 12px; margin: 20px 0; border: 1px solid #ddd;">
                        <h4 style="margin: 0 0 10px; color: #E60026; text-transform: uppercase;">Real-Time Location</h4>
                        <p style="margin: 0 0 15px; font-weight: bold;">{map_link}</p>
                        <a href="{map_link}" style="background: #111; color: white; padding: 12px 20px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Open in Google Maps</a>
                    </div>

                    <div style="background: #FFF5F6; padding: 20px; border-radius: 12px; border-left: 5px solid #E60026;">
                        <h4 style="margin: 0 0 10px; color: #720000;">Dating History Context</h4>
                        <p style="margin: 0; color: #4A0008; font-size: 15px; line-height: 1.5;">
                            {date_context}
                        </p>
                    </div>

                    <p style="color: #888; font-size: 12px; margin-top: 30px; text-align: center; font-weight: bold;">
                        This alert was triggered via the FIND YOUR MATCH Emergency SOS system.
                    </p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content, sender_name="FYM EMERGENCY BROADCAST")


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
