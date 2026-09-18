import os
import logging
import smtplib
import textwrap
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formataddr, formatdate, make_msgid

logger = logging.getLogger(__name__)

# Define standard sender name for consistency
SENDER_NAME_DEFAULT = "FIND YOUR MATCH AI"

import ssl

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
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain="findyourmatch.co.ke")

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
        # Many shared hosting providers (like cPanel) have self-signed or mismatched certs for mail.domain.com
        context = ssl._create_unverified_context()
        
        if smtp_port == 465:
            # Use context manager (with) to safely close connection even on failure
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
                server.login(sender_email, sender_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls(context=context)
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


def send_monday_matches_email(recipient_email, recipient_name, perfect_matches):
    """
    Sends the weekly Monday Perfect Matches recommendation email containing contact details,
    compatibility, university bio, and direct profile view links of top opposite-sex matches.
    """
    subject = "💌 Monday Love Sheet: Your Perfect Matches & Contact Details!"
    base_url = os.getenv("BASE_URL", "https://match-ai.onrender.com").rstrip('/')
    
    # 1. Build Matches HTML blocks with view profile CTA button
    matches_html = ""
    for m in perfect_matches:
        profile_url = f"{base_url}/student/{m['id']}"
        matches_html += f"""
        <div style="background: #FFF5F6; border: 1px solid #FFD6DD; border-radius: 16px; padding: 20px; margin-bottom: 25px; text-align: left; box-shadow: 0 4px 10px rgba(230,0,38,0.02);">
            <h3 style="color: #720000; margin: 0 0 5px 0; font-size: 18px; font-weight: 900;">🔥 {m['name']} ({m['compatibility']}% Compatibility)</h3>
            <p style="margin: 0 0 10px 0; font-size: 13px; font-weight: 700; color: #E60026; text-transform: uppercase;">🎓 {m['course']} at {m['institution']}</p>
            <p style="margin: 0 0 15px 0; font-size: 14px; color: #555; font-style: italic; line-height: 1.5;">"{m['bio']}"</p>
            
            <div style="background: white; border-radius: 12px; padding: 15px; border: 1px dashed #FFD6DD; font-size: 13px; color: #333; margin-bottom: 15px;">
                <p style="margin: 4px 0; font-size: 14px;"><strong>📞 Phone Number:</strong> <a href="tel:{m['phone']}" style="color: #E60026; text-decoration: none; font-weight: 900;">+{m['phone']}</a></p>
                <p style="margin: 4px 0; font-size: 14px;"><strong>✉️ Email Address:</strong> <a href="mailto:{m['email']}" style="color: #E60026; text-decoration: none; font-weight: 900;">{m['email']}</a></p>
                <p style="margin: 8px 0 0 0; color: #777; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">🪐 Zodiac: <strong>{m.get('zodiac', 'Not specified')}</strong> | 🌌 MBTI: <strong>{m.get('mbti', 'Not specified')}</strong></p>
            </div>
            
            <div style="text-align: center;">
                <a href="{profile_url}" style="background: linear-gradient(135deg, #E60026 0%, #720000 100%); color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-weight: 900; font-size: 13px; display: inline-block; box-shadow: 0 4px 12px rgba(230,0,38,0.25);">
                    👤 Click to View Profile
                </a>
            </div>
        </div>
        """

    # 2. Build plain text fallback
    matches_text = ""
    for m in perfect_matches:
        profile_url = f"{base_url}/student/{m['id']}"
        matches_text += f"- {m['name']} ({m['compatibility']}%): study {m['course']} at {m['institution']}. Phone: +{m['phone']}, Email: {m['email']}. Bio: {m['bio']}. View: {profile_url}\n\n"

    text_content = textwrap.dedent(f"""\
        Hello {recipient_name}!
        
        It's Monday! The FYM perfect matchmaking algorithm has compiled your compatibility reports.
        Below are your top perfect matches on campus along with their contact details. Click the links below to view their profiles:
        
        {matches_text}
        
        Safety Reminder: Always meet your matches in well-lit, public university hotspots (like the library foyer or student union square).
        
        Have fun!
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 24px; border-top: 8px solid #E60026; box-shadow: 0 15px 35px rgba(114,0,0,0.06);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="font-size: 45px;">💌</span>
                </div>
                
                <h2 style="color: #720000; margin-top: 0; font-size: 26px; font-weight: 950; text-align: center; letter-spacing: -1px;">Monday Love Match Sheet!</h2>
                <p style="color: #555; font-size: 16px; line-height: 1.6; text-align: center; font-weight: 500; margin-bottom: 30px;">
                    Hello <strong>{recipient_name}</strong>, it is Monday! To help you secure a date this week, the FYM algorithm has retrieved your top opposite-sex perfect matches (>80% compatibility) with their contact cards. Click to view their profiles!
                </p>
                
                <!-- === PERFECT MATCHES CARDS === -->
                {matches_html}
                
                <!-- === SAFETY NOTICE === -->
                <div style="background: #FFFbeb; border: 1px solid #fef3c7; border-radius: 16px; padding: 15px; margin-top: 30px; font-size: 13px; color: #b45309; line-height: 1.5;">
                    🛡️ <strong>Safety Coordinator Advisory:</strong> To keep MMUST and partner campus students secure, we strongly advise meeting for dates only in verified public venues (e.g. library courtyards, college cafeterias, or partner cafes listed in Date Spots).
                </div>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    Have an amazing week! <br>
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_friday_matches_email(recipient_email, recipient_name, perfect_matches):
    """
    Sends the weekly Friday Perfect Matches recommendation email containing contact details,
    compatibility, university bio, and direct profile view links of top 50 opposite-sex matches.
    """
    subject = "💌 Friday Perfect Matches: Your Weekend Matchmaking Sheet!"
    base_url = os.getenv("BASE_URL", "https://match-ai.onrender.com").rstrip('/')
    
    # 1. Build Matches HTML blocks with view profile CTA button
    matches_html = ""
    for m in perfect_matches:
        profile_url = f"{base_url}/student/{m['id']}"
        matches_html += f"""
        <div style="background: #FFF5F6; border: 1px solid #FFD6DD; border-radius: 16px; padding: 20px; margin-bottom: 25px; text-align: left; box-shadow: 0 4px 10px rgba(230,0,38,0.02);">
            <h3 style="color: #720000; margin: 0 0 5px 0; font-size: 18px; font-weight: 900;">🔥 {m['name']} ({m['compatibility']}% Compatibility)</h3>
            <p style="margin: 0 0 10px 0; font-size: 13px; font-weight: 700; color: #E60026; text-transform: uppercase;">🎓 {m['course']} at {m['institution']}</p>
            <p style="margin: 0 0 15px 0; font-size: 14px; color: #555; font-style: italic; line-height: 1.5;">"{m['bio']}"</p>
            
            <div style="background: white; border-radius: 12px; padding: 15px; border: 1px dashed #FFD6DD; font-size: 13px; color: #333; margin-bottom: 15px;">
                <p style="margin: 4px 0; font-size: 14px;"><strong>📞 Phone Number:</strong> <a href="tel:{m['phone']}" style="color: #E60026; text-decoration: none; font-weight: 900;">+{m['phone']}</a></p>
                <p style="margin: 4px 0; font-size: 14px;"><strong>✉️ Email Address:</strong> <a href="mailto:{m['email']}" style="color: #E60026; text-decoration: none; font-weight: 900;">{m['email']}</a></p>
                <p style="margin: 8px 0 0 0; color: #777; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">🪐 Zodiac: <strong>{m.get('zodiac', 'Not specified')}</strong> | 🌌 MBTI: <strong>{m.get('mbti', 'Not specified')}</strong></p>
            </div>
            
            <div style="text-align: center;">
                <a href="{profile_url}" style="background: linear-gradient(135deg, #E60026 0%, #720000 100%); color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; font-weight: 900; font-size: 13px; display: inline-block; box-shadow: 0 4px 12px rgba(230,0,38,0.25);">
                    👤 Click to View Profile
                </a>
            </div>
        </div>
        """

    # 2. Build plain text fallback
    matches_text = ""
    for m in perfect_matches:
        profile_url = f"{base_url}/student/{m['id']}"
        matches_text += f"- {m['name']} ({m['compatibility']}%): study {m['course']} at {m['institution']}. Phone: +{m['phone']}, Email: {m['email']}. Bio: {m['bio']}. View: {profile_url}\n\n"

    text_content = textwrap.dedent(f"""\
        Hello {recipient_name}!
        
        It's Friday! The FYM weekend matchmaker has compiled your compatibility reports.
        Below are your top 50 perfect matches (>80% compatibility) on campus with contact details. Make your move before Lights Out!
        
        {matches_text}
        
        Safety Reminder: Always meet your matches in well-lit, public university hotspots (like the library foyer or student union square).
        
        Have fun!
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 24px; border-top: 8px solid #a855f7; box-shadow: 0 15px 35px rgba(138,43,226,0.06);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="font-size: 45px;">💖</span>
                </div>
                
                <h2 style="color: #4b0082; margin-top: 0; font-size: 26px; font-weight: 950; text-align: center; letter-spacing: -1px;">Friday Perfect Match Sheet!</h2>
                <p style="color: #555; font-size: 16px; line-height: 1.6; text-align: center; font-weight: 500; margin-bottom: 30px;">
                    Hello <strong>{recipient_name}</strong>, it is Friday! To prepare you for the weekend, the FYM algorithm has scanned the network and compiled your top 50 opposite-sex perfect matches (>80% compatibility) with contact cards. Make your move before the Friday Lights Out lobby opens!
                </p>
                
                <!-- === PERFECT MATCHES CARDS === -->
                {matches_html}
                
                <!-- === SAFETY NOTICE === -->
                <div style="background: #FFFbeb; border: 1px solid #fef3c7; border-radius: 16px; padding: 15px; margin-top: 30px; font-size: 13px; color: #b45309; line-height: 1.5;">
                    🛡️ <strong>Safety Coordinator Advisory:</strong> To keep MMUST and partner campus students secure, we strongly advise meeting for dates only in verified public venues (e.g. library courtyards, college cafeterias, or partner cafes listed in Date Spots).
                </div>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    Have an amazing weekend! <br>
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_spotify_playlist_email(recipient_email, recipient_name, sender_name, playlist_url):
    """
    Dispatches a flirty retro mixtape cassette email when a user shares their Spotify playlist with a partner.
    """
    subject = f"🎵 {sender_name} sent you a romantic Spotify Playlist Mixtape!"
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name}!
        
        {sender_name} has shared a flirty dating mixtape playlist with you on Spotify!
        Listen to it here: {playlist_url}
        
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 24px; border-top: 8px solid #1DB954; box-shadow: 0 15px 35px rgba(0,0,0,0.06);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="font-size: 45px;">🎵</span>
                </div>
                
                <h2 style="color: #1DB95Green; margin-top: 0; font-size: 26px; font-weight: 950; text-align: center; letter-spacing: -1px; color: #1DB954;">Spotify Mixtape Shared!</h2>
                
                <div style="background: #191414; color: white; border-radius: 20px; padding: 30px 20px; text-align: center; position: relative; border: 4px solid #1DB954; margin: 25px 0; box-shadow: 0 8px 25px rgba(29,185,84,0.15);">
                    <div style="width: 120px; height: 10px; background: #333; margin: 0 auto 20px auto; border-radius: 10px;"></div>
                    <div style="font-size: 13px; font-weight: 900; color: #1DB954; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 5px;">Retro Cassette Mixtape</div>
                    <div style="font-size: 20px; font-weight: 950; color: #fff; margin-bottom: 25px;">⚡ {sender_name}'s Flirty Anthems</div>
                    
                    <a href="{playlist_url}" target="_blank" style="background: #1DB954; color: black; padding: 14px 28px; text-decoration: none; border-radius: 50px; font-weight: 950; font-size: 15px; display: inline-block; box-shadow: 0 4px 15px rgba(29,185,84,0.4);">
                        ▶️ Play Mix on Spotify
                    </a>
                </div>
                
                <p style="color: #333; font-size: 15px; line-height: 1.6; text-align: center;">
                    Hello <strong>{recipient_name}</strong>, music is the shortcut to connection! Your match <strong>{sender_name}</strong> wants to share their dating anthems with you. Click the green button above to connect and start listening together!
                </p>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    Listen and enjoy! <br>
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_meetup_request_email(recipient_email, recipient_name, sender_name):
    """
    Emails a target student notifying them that an opposite-gender classmate wishes to meet up geographically.
    """
    subject = f"📍 Flirty Alert: {sender_name} wants to meet up with you near campus!"
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name}!
        
        Exciting news! {sender_name} is geographically close and wants to meet up with you!
        Log in to your FIND YOUR MATCH dashboard to coordinate your meetup.
        
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 24px; border-top: 8px solid #E60026; box-shadow: 0 15px 35px rgba(114,0,0,0.06);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="font-size: 45px;">📍</span>
                </div>
                
                <h2 style="color: #720000; margin-top: 0; font-size: 26px; font-weight: 950; text-align: center; letter-spacing: -1px;">Geographic Meetup Requested!</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6; text-align: center; font-weight: 500;">
                    Hello <strong>{recipient_name}</strong>, exciting news! Your match <strong>{sender_name}</strong> is geographically nearby and has sent a premium meetup request!
                </p>
                
                <div style="background: #FEF2F4; border: 1px solid #FFD6DD; border-radius: 16px; padding: 20px; margin: 25px 0; text-align: center;">
                    <p style="color: #E60026; font-size: 16px; font-weight: 900; margin-top: 0;">📍 {sender_name} is close by!</p>
                    <p style="color: #4A0008; font-size: 14px; margin-bottom: 20px;">Do you want to meetup with them in a verified, public spot?</p>
                    
                    <a href="https://match-ai.onrender.com/dashboard" style="background: linear-gradient(135deg, #E60026 0%, #720000 100%); color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: 900; display: inline-block; box-shadow: 0 4px 12px rgba(230,0,38,0.25);">
                        💖 Open Dashboard & Respond
                    </a>
                </div>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    Safe dating is happy dating! <br>
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_proximity_meetup_email(recipient_email, recipient_name, nearby_matches):
    """
    Sends the Proximity Proximity Meetup Reveal email containing the profiles and images
    of opposite-sex Diamond users located within a 1 KM radius who agreed to meet.
    """
    subject = "🤝 Proximity Meetup Agreed! Nearby Match Profiles Revealed!"
    base_url = os.getenv("BASE_URL", "https://match-ai.onrender.com").rstrip('/')
    
    # 1. Build Matches HTML blocks with view profile CTA button
    matches_html = ""
    for m in nearby_matches:
        profile_url = f"{base_url}/student/{m['id']}"
        matches_html += f"""
        <div style="background: #FAF5FF; border: 1px solid #E9D5FF; border-radius: 16px; padding: 20px; margin-bottom: 25px; text-align: left; box-shadow: 0 4px 10px rgba(168,85,247,0.02); display: flex; align-items: center; gap: 20px;">
            <img src="{m['img']}" style="width: 80px; height: 80px; border-radius: 50%; object-fit: cover; border: 3px solid #E9D5FF; flex-shrink: 0;" alt="{m['name']}">
            <div>
                <h3 style="color: #4b0082; margin: 0 0 5px 0; font-size: 18px; font-weight: 900;">🔥 {m['name']} ({m['compatibility']}% Compatibility)</h3>
                <p style="margin: 0 0 5px 0; font-size: 13px; font-weight: 700; color: #a855f7; text-transform: uppercase;">🎓 {m['course']} at {m['institution']}</p>
                <p style="margin: 0 0 10px 0; font-size: 13px; color: #666; font-style: italic;">"{m['bio']}"</p>
                
                <div style="background: white; border-radius: 10px; padding: 10px; border: 1px dashed #E9D5FF; font-size: 12px; color: #333; margin-bottom: 10px;">
                    <p style="margin: 2px 0;"><strong>📞 Phone:</strong> <a href="tel:{m['phone']}" style="color: #a855f7; text-decoration: none; font-weight: bold;">+{m['phone']}</a></p>
                    <p style="margin: 2px 0;"><strong>✉️ Email:</strong> <a href="mailto:{m['email']}" style="color: #a855f7; text-decoration: none; font-weight: bold;">{m['email']}</a></p>
                </div>
                
                <a href="{profile_url}" style="background: linear-gradient(135deg, #a855f7 0%, #7e22ce 100%); color: white; padding: 6px 14px; text-decoration: none; border-radius: 6px; font-weight: 900; font-size: 12px; display: inline-block; box-shadow: 0 2px 8px rgba(168,85,247,0.2);">
                    👤 View Profile
                </a>
            </div>
        </div>
        """

    # 2. Build plain text fallback
    matches_text = ""
    for m in nearby_matches:
        profile_url = f"{base_url}/student/{m['id']}"
        matches_text += f"- {m['name']} ({m['compatibility']}%): {m['course']} at {m['institution']}. Phone: +{m['phone']}, Email: {m['email']}. View: {profile_url}\n\n"

    text_content = textwrap.dedent(f"""\
        Hello {recipient_name}!
        
        Fantastic news! You and a nearby student have agreed to meet up and physically talk!
        Below are the profiles and images of opposite-sex premium comrades detected within a 1 KM radius of your location:
        
        {matches_text}
        
        Enjoy your meetup! Meet in a safe, public campus spot.
        
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 24px; border-top: 8px solid #a855f7; box-shadow: 0 15px 35px rgba(138,43,226,0.06);">
                <div style="text-align: center; margin-bottom: 20px;">
                    <span style="font-size: 45px;">🤝</span>
                </div>
                
                <h2 style="color: #4b0082; margin-top: 0; font-size: 26px; font-weight: 950; text-align: center; letter-spacing: -1px;">Meetup Confirmed! 📍</h2>
                <p style="color: #555; font-size: 16px; line-height: 1.6; text-align: center; font-weight: 500; margin-bottom: 30px;">
                    Hello <strong>{recipient_name}</strong>! You and a nearby premium comrade have both clicked **Yes** to meet up and physically talk! 
                    As promised, here are the profiles and pictures of active matches detected within a **1 KM radius** of your coordinates:
                </p>
                
                <!-- === MATCHES CARDS === -->
                {matches_html}
                
                <!-- === SAFETY NOTICE === -->
                <div style="background: #FFFbeb; border: 1px solid #fef3c7; border-radius: 16px; padding: 15px; margin-top: 30px; font-size: 13px; color: #b45309; line-height: 1.5;">
                    🛡️ <strong>Safety Advisory:</strong> Meet for physical talks strictly in well-populated campus spots (e.g. Student Union, university Library, CBD Partner Cafes). Stay safe and enjoy your conversation!
                </div>
                
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    Have a wonderful conversation! <br>
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_male_campaign_email(recipient_email, recipient_name):
    """
    Sends the September 2025 online community campaign invitation email to male users.
    Informs them about the Google Meet event and asks them to RSVP by replying.
    """
    subject = "🔥 You're Invited: Find Your Match Online Community Campaign!"

    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},

        Big News from the Find Your Match Community! 🎉

        We are excited to announce an exclusive online community campaign — a special virtual
        event where members of the Find Your Match family will come together to connect,
        interact, and get to know each other in a whole new way!

        This is your moment to be part of something truly special. Whether you're looking to
        make new friends, meaningful connections, or find your perfect match — this event was
        made for you.

        📅 EVENT DETAILS:
        ─────────────────────────────────
        📆 Date    : Sunday, 7th September 2025
        🕘 Time    : 9:00 PM EAT (East Africa Time)
        💻 Platform: Google Meet
        🔗 Link    : https://meet.google.com/rgc-cjov-jda
        ─────────────────────────────────

        👉 ACTION REQUIRED:
        Please reply to this email to confirm whether you will be attending.
        Your RSVP helps us prepare adequately and ensures your spot is reserved!

        We look forward to seeing you online. Let's make great connections together! 💪

        Warm regards,
        The {SENDER_NAME_DEFAULT} Team 💌
    """)

    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 24px; overflow: hidden; box-shadow: 0 15px 40px rgba(114,0,0,0.10);">

                <!-- HEADER -->
                <div style="background: linear-gradient(135deg, #720000 0%, #E60026 100%); padding: 50px 30px; text-align: center;">
                    <div style="font-size: 52px; margin-bottom: 15px;">🔥</div>
                    <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.3;">
                        FYM Online Community Campaign
                    </h1>
                    <p style="color: rgba(255,255,255,0.85); margin: 12px 0 0; font-size: 16px; font-weight: 500;">
                        You're officially invited! 🎉
                    </p>
                </div>

                <!-- BODY -->
                <div style="padding: 40px 35px;">
                    <p style="font-size: 17px; color: #333; line-height: 1.7; margin-top: 0;">
                        Hello <strong style="color: #720000;">{recipient_name}</strong>,
                    </p>
                    <p style="font-size: 16px; color: #555; line-height: 1.7;">
                        We are thrilled to announce an exclusive <strong>online community campaign</strong> — a special virtual event where the entire Find Your Match family will come together to <strong>connect, interact, and get to know each other</strong> in a whole new way!
                    </p>
                    <p style="font-size: 16px; color: #555; line-height: 1.7;">
                        Whether you're looking to make new friends, meaningful connections, or find your perfect match — <strong>this event was made for you.</strong>
                    </p>

                    <!-- EVENT DETAILS BOX -->
                    <div style="background: #FEF2F4; border: 1px solid #FFD6DD; border-radius: 16px; padding: 28px 30px; margin: 30px 0;">
                        <h3 style="color: #720000; margin: 0 0 18px 0; font-size: 18px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px;">📅 Event Details</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #4A0008; font-size: 15px; font-weight: 700; width: 120px;">📆 Date</td>
                                <td style="padding: 8px 0; color: #333; font-size: 15px;">Sunday, 7th September 2025</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #4A0008; font-size: 15px; font-weight: 700;">🕘 Time</td>
                                <td style="padding: 8px 0; color: #333; font-size: 15px;">9:00 PM EAT (East Africa Time)</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #4A0008; font-size: 15px; font-weight: 700;">💻 Platform</td>
                                <td style="padding: 8px 0; color: #333; font-size: 15px;">Google Meet</td>
                            </tr>
                        </table>
                        <!-- JOIN BUTTON -->
                        <div style="text-align: center; margin-top: 22px;">
                            <a href="https://meet.google.com/rgc-cjov-jda" target="_blank"
                               style="background: linear-gradient(135deg, #E60026 0%, #720000 100%); color: white; padding: 14px 32px; text-decoration: none; border-radius: 50px; font-weight: 900; font-size: 16px; display: inline-block; box-shadow: 0 6px 20px rgba(230,0,38,0.35); letter-spacing: 0.3px;">
                                🔗 Click to Join Google Meet
                            </a>
                        </div>
                    </div>

                    <!-- RSVP NOTICE -->
                    <div style="background: #fffbeb; border: 1px solid #fef3c7; border-left: 5px solid #f59e0b; border-radius: 12px; padding: 18px 20px; margin: 25px 0;">
                        <p style="margin: 0; color: #92400e; font-size: 15px; line-height: 1.6;">
                            <strong>👉 ACTION REQUIRED:</strong> Please <strong>reply to this email</strong> to confirm whether you will be attending the event. Your RSVP helps us prepare and reserve your spot!
                        </p>
                    </div>

                    <p style="color: #555; font-size: 15px; line-height: 1.7; text-align: center; margin-top: 30px;">
                        We look forward to seeing you online.<br>Let's make great connections together! 💪
                    </p>
                </div>

                <!-- FOOTER -->
                <div style="background: #fafafa; padding: 25px 30px; text-align: center; border-top: 1px solid #eee;">
                    <p style="margin: 0 0 6px; font-size: 12px; color: #aaa; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">
                        FIND YOUR MATCH AI — Powered Dating
                    </p>
                    <p style="margin: 0; font-size: 11px; color: #ccc;">
                        &copy; {datetime.now().year} Delstarford Works. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_female_campaign_email(recipient_email, recipient_name):
    """
    Sends the September 2025 online community campaign email to female users.
    Includes the Google Meet event invite, profile update request, and work opportunity notice.
    """
    subject = "💌 You're Invited: FYM Online Campaign + Important Update & Opportunity!"

    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},

        Exciting Updates from the Find Your Match Team! 🌟
        Please read through carefully — there are 3 important things for you!

        ─────────────────────────────────────────────────
        🎉 PART 1: JOIN OUR ONLINE COMMUNITY CAMPAIGN!
        ─────────────────────────────────────────────────
        We are hosting an exclusive online community campaign — a special virtual event
        where the entire Find Your Match family will come together to connect, interact,
        and get to know each other like never before!

        📅 EVENT DETAILS:
        📆 Date    : Sunday, 7th September 2025
        🕘 Time    : 9:00 PM EAT (East Africa Time)
        💻 Platform: Google Meet
        🔗 Link    : https://meet.google.com/rgc-cjov-jda

        👉 Please reply to this email to confirm your attendance!

        ─────────────────────────────────────────────────
        📝 PART 2: UPDATE YOUR PROFILE
        ─────────────────────────────────────────────────
        We are raising the bar on profile quality! Kindly go to your Profile Section
        and make sure the following are updated:
          ✅ Profile Photo  — Upload a clear, recent photo of yourself
          ✅ Phone Number   — Ensure your phone number is correctly added

        A complete profile puts you front and centre for the best matches!

        ─────────────────────────────────────────────────
        💼 PART 3: EXCITING WORK OPPORTUNITY!
        ─────────────────────────────────────────────────
        We are looking for confident and enthusiastic ladies in our community who are
        ready to be part of the Find Your Match team in an exciting upcoming role!

        If you are ready and interested, simply reply to this email with:
                        READY TO WORK
        ...and our team will reach out with all the details.

        ─────────────────────────────────────────────────

        Thank you for being a valued part of our community. We can't wait to see you
        at the event and hear from you! 💪

        With love,
        The {SENDER_NAME_DEFAULT} Team 💌
    """)

    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f4f6f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 24px; overflow: hidden; box-shadow: 0 15px 40px rgba(114,0,0,0.10);">

                <!-- HEADER -->
                <div style="background: linear-gradient(135deg, #720000 0%, #E60026 50%, #ff6b9d 100%); padding: 50px 30px; text-align: center;">
                    <div style="font-size: 52px; margin-bottom: 15px;">💌</div>
                    <h1 style="color: white; margin: 0; font-size: 26px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.3;">
                        Important Updates Just For You!
                    </h1>
                    <p style="color: rgba(255,255,255,0.85); margin: 12px 0 0; font-size: 15px; font-weight: 500;">
                        3 exciting things inside — please read carefully 🌟
                    </p>
                </div>

                <!-- BODY -->
                <div style="padding: 40px 35px;">
                    <p style="font-size: 17px; color: #333; line-height: 1.7; margin-top: 0;">
                        Hello <strong style="color: #720000;">{recipient_name}</strong>,
                    </p>
                    <p style="font-size: 15px; color: #555; line-height: 1.7; margin-bottom: 30px;">
                        We have some amazing news and important requests for you. Please read through all three sections below!
                    </p>

                    <!-- PART 1 — CAMPAIGN -->
                    <div style="border-left: 5px solid #E60026; padding-left: 18px; margin-bottom: 30px;">
                        <h2 style="color: #E60026; font-size: 17px; font-weight: 900; margin: 0 0 10px 0; text-transform: uppercase; letter-spacing: 0.5px;">🎉 Part 1: Online Community Campaign</h2>
                    </div>

                    <p style="font-size: 15px; color: #555; line-height: 1.7; margin-top: 0;">
                        We are hosting an exclusive <strong>online community campaign</strong> — a special virtual event where the entire Find Your Match family will come together to <strong>connect, interact, and get to know each other</strong> like never before! Don't miss out!
                    </p>

                    <!-- EVENT DETAILS BOX -->
                    <div style="background: #FEF2F4; border: 1px solid #FFD6DD; border-radius: 16px; padding: 28px 30px; margin: 20px 0 30px 0;">
                        <h3 style="color: #720000; margin: 0 0 18px 0; font-size: 16px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px;">📅 Event Details</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #4A0008; font-size: 14px; font-weight: 700; width: 110px;">📆 Date</td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px;">Sunday, 7th September 2025</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #4A0008; font-size: 14px; font-weight: 700;">🕘 Time</td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px;">9:00 PM EAT (East Africa Time)</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #4A0008; font-size: 14px; font-weight: 700;">💻 Platform</td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px;">Google Meet</td>
                            </tr>
                        </table>
                        <div style="text-align: center; margin-top: 22px;">
                            <a href="https://meet.google.com/rgc-cjov-jda" target="_blank"
                               style="background: linear-gradient(135deg, #E60026 0%, #720000 100%); color: white; padding: 13px 30px; text-decoration: none; border-radius: 50px; font-weight: 900; font-size: 15px; display: inline-block; box-shadow: 0 6px 20px rgba(230,0,38,0.35);">
                                🔗 Click to Join Google Meet
                            </a>
                        </div>
                    </div>

                    <div style="background: #fffbeb; border: 1px solid #fef3c7; border-left: 5px solid #f59e0b; border-radius: 12px; padding: 16px 18px; margin-bottom: 35px;">
                        <p style="margin: 0; color: #92400e; font-size: 14px; line-height: 1.6;">
                            <strong>👉 ACTION REQUIRED:</strong> Please <strong>reply to this email</strong> to confirm your attendance. Your RSVP helps us prepare!
                        </p>
                    </div>

                    <!-- DIVIDER -->
                    <hr style="border: none; border-top: 2px dashed #FFD6DD; margin: 0 0 30px 0;">

                    <!-- PART 2 — PROFILE UPDATE -->
                    <div style="border-left: 5px solid #720000; padding-left: 18px; margin-bottom: 15px;">
                        <h2 style="color: #720000; font-size: 17px; font-weight: 900; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">📝 Part 2: Update Your Profile</h2>
                    </div>
                    <p style="font-size: 15px; color: #555; line-height: 1.7;">
                        We are improving profile quality across the platform. Please head to your <strong>Profile Section</strong> and ensure these are up to date:
                    </p>
                    <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 18px 22px; margin: 15px 0 30px 0;">
                        <p style="margin: 6px 0; color: #166534; font-size: 15px;">✅ <strong>Profile Photo</strong> — Upload a clear, recent photo of yourself</p>
                        <p style="margin: 6px 0; color: #166534; font-size: 15px;">✅ <strong>Phone Number</strong> — Ensure your phone number is correctly added</p>
                    </div>

                    <!-- DIVIDER -->
                    <hr style="border: none; border-top: 2px dashed #FFD6DD; margin: 0 0 30px 0;">

                    <!-- PART 3 — WORK OPPORTUNITY -->
                    <div style="border-left: 5px solid #7c3aed; padding-left: 18px; margin-bottom: 15px;">
                        <h2 style="color: #7c3aed; font-size: 17px; font-weight: 900; margin: 0; text-transform: uppercase; letter-spacing: 0.5px;">💼 Part 3: Work Opportunity</h2>
                    </div>
                    <p style="font-size: 15px; color: #555; line-height: 1.7;">
                        We are looking for <strong>confident and enthusiastic ladies</strong> within our community who are ready to join the Find Your Match team in an exciting upcoming role!
                    </p>
                    <div style="background: #faf5ff; border: 1px solid #e9d5ff; border-radius: 12px; padding: 20px 22px; margin: 15px 0 30px 0; text-align: center;">
                        <p style="margin: 0 0 10px; color: #6b21a8; font-size: 15px; line-height: 1.6;">
                            If you are <strong>ready and interested</strong>, simply reply to this email with:
                        </p>
                        <div style="background: #7c3aed; color: white; font-size: 20px; font-weight: 900; letter-spacing: 3px; padding: 16px 30px; border-radius: 12px; display: inline-block; margin: 5px 0;">
                            READY TO WORK
                        </div>
                        <p style="margin: 12px 0 0; color: #888; font-size: 13px;">Our team will reach out with all the details!</p>
                    </div>

                    <p style="color: #555; font-size: 15px; line-height: 1.7; text-align: center; margin-top: 10px;">
                        Thank you for being a valued member of our community.<br>We can't wait to see you at the event! 💪
                    </p>
                </div>

                <!-- FOOTER -->
                <div style="background: #fafafa; padding: 25px 30px; text-align: center; border-top: 1px solid #eee;">
                    <p style="margin: 0 0 6px; font-size: 12px; color: #aaa; font-weight: 800; text-transform: uppercase; letter-spacing: 1px;">
                        FIND YOUR MATCH AI — Powered Dating
                    </p>
                    <p style="margin: 0; font-size: 11px; color: #ccc;">
                        &copy; {datetime.now().year} Delstarford Works. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)
