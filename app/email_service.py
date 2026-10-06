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
SENDER_NAME_DEFAULT = "FIND YOUR MATCH"

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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                
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
                        FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .
                    </p>
                    <p style="margin: 0; font-size: 11px; color: #ccc;">
                        &copy; {datetime.now().year} Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .
                    </p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content, sender_name=SENDER_NAME_DEFAULT)


def send_manager_otp_email(recipient_email, otp_code):
    """Sends the 2FA OTP code to managers for secure portal access."""
    subject = "Manager Portal 2FA Code"
    body_text = f"Your one-time login code is: {otp_code}\nIt expires in 10 minutes."
    body_html = f"""
    <html>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <div style="max-width: 500px; margin: 40px auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
            <!-- HEADER -->
            <div style="background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%); padding: 30px; text-align: center;">
                <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">Security Check</h1>
            </div>
            
            <!-- BODY -->
            <div style="padding: 40px 30px; text-align: center;">
                <h2 style="margin: 0 0 15px; color: #0F172A; font-size: 20px; font-weight: 800;">Verify your login</h2>
                <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                    Please enter the following One-Time Password (OTP) to securely access the Manager Portal.
                </p>
                
                <div style="background: #f8fafc; border-radius: 12px; padding: 25px; margin: 0 auto 25px; border: 1px solid #e2e8f0; max-width: 250px;">
                    <div style="letter-spacing: 8px; font-size: 32px; font-weight: 900; color: #0ea5e9; margin: 0;">
                        {otp_code}
                    </div>
                </div>
                
                <p style="margin: 0; color: #ef4444; font-size: 13px; font-weight: 600;">
                    ⏱️ This code expires in 10 minutes.
                </p>
            </div>
            
            <!-- FOOTER -->
            <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0 0 5px; font-size: 12px; color: #94a3b8; font-weight: 800;">FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .</p>
            </div>
        </div>
    </body>
    </html>
    """
    return _send_email(recipient_email, subject, body_text, body_html, sender_name="FIND YOUR MATCH AI")

def send_group_join_request_email(admin_email, admin_name, user_name, group_name):
    """Notifies a group admin that a user wants to join their group."""
    subject = f"🔔 New Join Request for {group_name}"
    
    text_content = textwrap.dedent(f"""\
        Hi {admin_name},
        
        {user_name} has requested to join your group "{group_name}".
        Please log in to your account to review and approve their request.
        
        Review Request: {os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/groups
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin: 0; padding: 20px; font-family: sans-serif; background: #f4f6f8;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #720000; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                <h2 style="color: #0A2540;">New Join Request! 🔔</h2>
                <p style="color: #333; line-height: 1.5;">Hi {admin_name},</p>
                <p style="color: #333; line-height: 1.5;"><strong>{user_name}</strong> has requested to join your group <strong>{group_name}</strong>.</p>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/groups" style="display: inline-block; background-color: #E60026; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold;">Review Request</a>
                </div>
            </div>
        </body>
        </html>
    """)
    return _send_email(admin_email, subject, text_content, html_content, sender_name="FIND YOUR MATCH AI")

def send_group_notification_email(member_email, member_name, sender_name, group_name, message):
    """Notifies group members of a new message or update."""
    subject = f"💬 New Message in {group_name}"
    
    text_content = textwrap.dedent(f"""\
        Hi {member_name},
        
        You have a new notification in {group_name} from {sender_name}:
        "{message}"
        
        Check it out: {os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/groups
    """)
    
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="margin: 0; padding: 20px; font-family: sans-serif; background: #f4f6f8;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #720000; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                <h2 style="color: #0A2540;">New Group Notification 💬</h2>
                <p style="color: #333; line-height: 1.5;">Hi {member_name},</p>
                <p style="color: #333; line-height: 1.5;">You have a new message in <strong>{group_name}</strong> from <strong>{sender_name}</strong>:</p>
                <div style="background: #FEF2F4; padding: 15px; border-radius: 10px; margin: 20px 0; color: #555; font-style: italic;">"{message}"</div>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/groups" style="display: inline-block; background-color: #E60026; color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold;">View Group</a>
                </div>
            </div>
        </body>
        </html>
    """)
    return _send_email(member_email, subject, text_content, html_content, sender_name="FIND YOUR MATCH AI")

def send_group_invite_email(to_email, user_name, group_name, admin_name):
    """Sends a professional welcome email when added to a group."""
    subject = f"💬 You've been invited to join {group_name}!"
    
    text_content = textwrap.dedent(f"""\
        Welcome, {user_name}!
        
        You have been invited to join the group {group_name} by {admin_name}. 
        We are wishing you the absolute best in finding your perfect match!
        
        Group Rules:
        - Be respectful and kind to everyone.
        - Shoot your shot, but take 'no' gracefully.
        - Have fun and keep the vibes immaculate!
        
        Enter the Chat: {os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/groups
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <h2 style="color: #0A2540; margin-top: 0; font-size: 22px;">Welcome, {user_name}! 🎉</h2>
                <p style="color: #333; font-size: 16px; line-height: 1.5;">
                    You have been invited to join the group <strong>{group_name}</strong> by {admin_name}. 
                    We are wishing you the absolute best in finding your perfect match!
                </p>
                <div style="background: #FEF2F4; padding: 15px; border-radius: 10px; margin: 20px 0;">
                    <strong style="color: #720000; font-size: 14px; text-transform: uppercase;">📜 Group Rules</strong>
                    <ul style="color: #555; margin: 10px 0 0 0; font-size: 14px;">
                        <li>Be respectful and kind to everyone.</li>
                        <li>Shoot your shot, but take 'no' gracefully.</li>
                        <li>Have fun and keep the vibes immaculate!</li>
                    </ul>
                </div>
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{{ url_for('groups', _external=True) }}" style="background: #38BDF8; color: #0A2540; font-weight: 800; text-decoration: none; padding: 15px 30px; border-radius: 50px; display: inline-block;">Enter the Chat</a>
                </div>
            </div>
        </body>
        </html>
    """)
    
    return _send_email(to_email, subject, text_content, html_content)


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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <h2 style="color: #720000; margin-top: 0; font-size: 22px; font-weight: 900;">New Date Proposal! 🍽️</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    Hello <strong>{merchant_name}</strong>, a new couple wants to meet at your venue.
                </p>
                
                <div style="background: #fafafa; padding: 20px; border-radius: 12px; border: 1px solid #eee; margin: 25px 0;">
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>Couple:</strong> {user_a_name} & {user_b_name}</p>
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>Proposed Time:</strong> {date_day} at {date_time}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/business/login" style="background: #720000; color: white; padding: 14px 25px; text-decoration: none; border-radius: 8px; font-weight: 900; display: inline-block;">
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


def send_date_request_to_partner_email(partner_email, merchant_name, user_a_name, user_b_name, date_day, date_time):
    """Sends a notification email to the partner when a new date is proposed to them."""
    subject = f"💌 {user_a_name} invited you on a date!"
    
    text_content = textwrap.dedent(f"""\
        Hello {user_b_name},
        
        Exciting news! {user_a_name} has just invited you on a date.
        
        Venue: {merchant_name}
        Proposed Time: {date_day} at {date_time}
        
        Please log in to your account and check your messages to accept the date!
        
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #e11d48; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <h2 style="color: #e11d48; margin-top: 0; font-size: 22px; font-weight: 900;">You have a Date Invitation! 💌</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    Hello <strong>{user_b_name}</strong>, big news! <strong>{user_a_name}</strong> wants to take you out on a date!
                </p>
                
                <div style="background: #fff1f2; padding: 20px; border-radius: 12px; border: 1px solid #fecdd3; margin: 25px 0;">
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>Venue:</strong> {merchant_name}</p>
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>When:</strong> {date_day} at {date_time}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/login" style="background: #e11d48; color: white; padding: 14px 25px; text-decoration: none; border-radius: 8px; font-weight: 900; display: inline-block;">
                        Open Chats to Reply
                    </a>
                </div>
                
                <p style="color: #888; font-size: 13px; margin-top: 30px; text-align: center;">
                    Don't leave them hanging! Open the app to chat and confirm the date.
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(partner_email, subject, text_content, html_content)


def send_date_request_to_sender_email(sender_email, merchant_name, user_a_name, user_b_name, date_day, date_time):
    """Sends a confirmation email to the sender that their date request was dispatched."""
    subject = f"Date Proposal Sent to {user_b_name}!"
    
    text_content = textwrap.dedent(f"""\
        Hello {user_a_name},
        
        Your date invitation has been sent successfully to {user_b_name} and the venue ({merchant_name})!
        
        Venue: {merchant_name}
        Proposed Time: {date_day} at {date_time}
        
        We'll let you know once they reply.
        
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
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #10b981; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <h2 style="color: #10b981; margin-top: 0; font-size: 22px; font-weight: 900;">Invitation Sent! 🎉</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.6;">
                    Hello <strong>{user_a_name}</strong>, your date invitation was delivered to <strong>{user_b_name}</strong> and <strong>{merchant_name}</strong>!
                </p>
                
                <div style="background: #ecfdf5; padding: 20px; border-radius: 12px; border: 1px solid #a7f3d0; margin: 25px 0;">
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>Venue:</strong> {merchant_name}</p>
                    <p style="margin: 8px 0; color: #111; font-size: 15px;"><strong>When:</strong> {date_day} at {date_time}</p>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/login" style="background: #10b981; color: white; padding: 14px 25px; text-decoration: none; border-radius: 8px; font-weight: 900; display: inline-block;">
                        Check Messages
                    </a>
                </div>
                
                <p style="color: #888; font-size: 13px; margin-top: 30px; text-align: center;">
                    Fingers crossed! We'll notify you as soon as they reply.
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(sender_email, subject, text_content, html_content)

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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>

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
                        &copy; {datetime.now().year} Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .
                    </p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_female_promo_campaign_email(recipient_email, recipient_name):
    """
    Sep 2026 Female Free Access Promo campaign email.
    Informs female users of:
      1. 1 month free access (already-registered) / 2 months free (new)
      2. New features: opposite-gender filtering on dashboard & talk
      3. Referral CTA - invite friends to Find Your Match
    """
    first_name = (recipient_name or 'there').split(' ')[0].strip()
    referral_link = f"https://findyourmatch.co.ke/signup"
    dashboard_link = "https://findyourmatch.co.ke/dashboard"

    subject = f"🎉 {first_name}, You Have FREE Premium Access! + Exciting New Updates!"

    text_content = textwrap.dedent(f"""\
        Hello {first_name},

        Great news from the Find Your Match community!

        ─────────────────────────────────────────────────
        🎁 GIFT #1: YOU HAVE FREE PREMIUM ACCESS!
        ─────────────────────────────────────────────────
        As a valued female member of our community, we have
        activated FREE Premium access on your account!

          ✅ Already registered? You get 1 MONTH FREE (until Oct 23, 2026)
          ✅ Newly joining?     You get 2 MONTHS FREE when you verify your email!

        This offer is only available until October 23, 2026.
        Log in now and enjoy full premium features for free:
        {dashboard_link}

        ─────────────────────────────────────────────────
        ✨ NEW UPDATE #2: SEE ONLY YOUR PERFECT MATCHES!
        ─────────────────────────────────────────────────
        We've improved how matches work on our platform:

          👩‍❤️‍👨 Dashboard  - Now shows ONLY male matches for you
          📞 Live Talk    - Directory now shows ONLY males online
          📱 Scroll Cards - Fixed to scroll smoothly on mobile

        Your experience just got a major upgrade!

        ─────────────────────────────────────────────────
        💖 INVITE YOUR FRIENDS & GROW THE COMMUNITY!
        ─────────────────────────────────────────────────
        Do you have friends who are still single and looking?
        Share Find Your Match with them! Any female friend who
        signs up before October 23, 2026 also gets FREE access!

        Share this link:
        {referral_link}

        The more, the merrier — let’s build the biggest campus
        dating community in Kenya together! 🇰🇳

        With love,
        The Find Your Match Team 💌
        findyourmatch.co.ke
    """)

    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>You Have Free Premium Access!</title>
        </head>
        <body style="margin:0;padding:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
            <div style="max-width:600px;margin:30px auto;background:white;border-radius:24px;overflow:hidden;box-shadow:0 15px 50px rgba(114,0,0,0.12);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>

                <!-- ===== HEADER ===== -->
                <div style="background:linear-gradient(135deg,#720000 0%,#E60026 60%,#ff6b9d 100%);padding:50px 30px 40px;text-align:center;">
                    <div style="font-size:60px;margin-bottom:12px;line-height:1;">&#x1F381;</div>
                    <h1 style="color:white;margin:0 0 10px;font-size:28px;font-weight:900;letter-spacing:-0.5px;line-height:1.3;">
                        You Have FREE Premium Access!
                    </h1>
                    <p style="color:rgba(255,255,255,0.9);margin:0;font-size:16px;font-weight:500;">
                        Plus exciting new updates just for you &#x1F31F;
                    </p>
                </div>

                <!-- ===== GREETING ===== -->
                <div style="padding:35px 35px 0;">
                    <p style="font-size:17px;color:#333;line-height:1.7;margin:0 0 6px;">
                        Hello <strong style="color:#720000;">{first_name}</strong>,
                    </p>
                    <p style="font-size:15px;color:#555;line-height:1.7;margin:0 0 30px;">
                        We have some amazing news for you from the <strong>Find Your Match</strong> community!
                        Read everything below &#x2014; there are 3 big updates just for you.
                    </p>
                </div>

                <!-- ===== SECTION 1: FREE ACCESS ===== -->
                <div style="margin:0 25px 25px;background:linear-gradient(135deg,#FEF2F4,#fff);border:2px solid #E60026;border-radius:20px;padding:28px 28px;">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                        <span style="font-size:36px;">&#x1F381;</span>
                        <h2 style="margin:0;color:#720000;font-size:20px;font-weight:900;">Gift #1: FREE Premium Access!</h2>
                    </div>
                    <p style="margin:0 0 18px;color:#444;font-size:15px;line-height:1.7;">
                        As a valued female member of our community, we've activated
                        <strong>FREE Premium</strong> on your account as a special thank-you gift!
                    </p>
                    <div style="background:white;border-radius:14px;padding:18px 20px;border:1px solid #FFD6DD;margin-bottom:20px;">
                        <div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:12px;">
                            <span style="font-size:22px;line-height:1;">&#x2705;</span>
                            <div>
                                <strong style="color:#720000;font-size:15px;display:block;">Already Registered?</strong>
                                <span style="color:#555;font-size:14px;">1 MONTH FREE &#x2014; valid until <strong>October 23, 2026</strong></span>
                            </div>
                        </div>
                        <div style="display:flex;align-items:flex-start;gap:12px;">
                            <span style="font-size:22px;line-height:1;">&#x2705;</span>
                            <div>
                                <strong style="color:#720000;font-size:15px;display:block;">Friends Joining Now?</strong>
                                <span style="color:#555;font-size:14px;">2 MONTHS FREE when they verify their email before Oct 23!</span>
                            </div>
                        </div>
                    </div>
                    <div style="text-align:center;">
                        <a href="{dashboard_link}" style="background:linear-gradient(135deg,#E60026 0%,#720000 100%);color:white;padding:15px 36px;text-decoration:none;border-radius:50px;font-weight:900;font-size:16px;display:inline-block;box-shadow:0 8px 25px rgba(230,0,38,0.35);letter-spacing:0.3px;">
                            &#x1F680; Go to My Dashboard
                        </a>
                    </div>
                </div>

                <!-- ===== SECTION 2: NEW FEATURES ===== -->
                <div style="margin:0 25px 25px;background:#f0f9ff;border:1.5px solid #bae6fd;border-radius:20px;padding:28px;">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                        <span style="font-size:36px;">&#x2728;</span>
                        <h2 style="margin:0;color:#0369a1;font-size:20px;font-weight:900;">Update #2: New Features!</h2>
                    </div>
                    <p style="margin:0 0 16px;color:#444;font-size:15px;line-height:1.7;">We've made big improvements to your experience on <strong>findyourmatch.co.ke</strong>:</p>
                    <div style="display:flex;flex-direction:column;gap:12px;">
                        <div style="background:white;border-radius:12px;padding:14px 16px;border:1px solid #e0f2fe;display:flex;gap:14px;align-items:flex-start;">
                            <span style="font-size:26px;line-height:1;flex-shrink:0;">&#x1F469;&#x200D;&#x2764;&#xFE0F;&#x200D;&#x1F468;</span>
                            <div><strong style="color:#0369a1;display:block;font-size:14px;">Dashboard &#x2014; Opposite Matches Only</strong><span style="color:#555;font-size:13px;">Your home feed now shows only male profiles &#x2014; no more confusion!</span></div>
                        </div>
                        <div style="background:white;border-radius:12px;padding:14px 16px;border:1px solid #e0f2fe;display:flex;gap:14px;align-items:flex-start;">
                            <span style="font-size:26px;line-height:1;flex-shrink:0;">&#x1F4DE;</span>
                            <div><strong style="color:#0369a1;display:block;font-size:14px;">Live Talk &#x2014; Males Only Visible</strong><span style="color:#555;font-size:13px;">The live directory now shows only males who are online right now.</span></div>
                        </div>
                        <div style="background:white;border-radius:12px;padding:14px 16px;border:1px solid #e0f2fe;display:flex;gap:14px;align-items:flex-start;">
                            <span style="font-size:26px;line-height:1;flex-shrink:0;">&#x1F4F1;</span>
                            <div><strong style="color:#0369a1;display:block;font-size:14px;">Smooth Mobile Scrolling</strong><span style="color:#555;font-size:13px;">Profile cards now scroll perfectly on your phone &#x2014; swipe to discover more!</span></div>
                        </div>
                    </div>
                </div>

                <!-- ===== SECTION 3: REFERRAL ===== -->
                <div style="margin:0 25px 30px;background:linear-gradient(135deg,#fdf4ff,#fce7f3);border:2px solid #e879f9;border-radius:20px;padding:28px;">
                    <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;">
                        <span style="font-size:36px;">&#x1F496;</span>
                        <h2 style="margin:0;color:#7e22ce;font-size:20px;font-weight:900;">Update #3: Invite Your Friends!</h2>
                    </div>
                    <p style="margin:0 0 16px;color:#444;font-size:15px;line-height:1.7;">
                        Do you have friends who are single and looking for meaningful connections?
                        <strong>Share Find Your Match with them</strong> today!
                    </p>
                    <div style="background:white;border-radius:14px;padding:18px 20px;border:1px solid #f0abfc;margin-bottom:20px;">
                        <p style="margin:0 0 10px;color:#7e22ce;font-size:14px;font-weight:900;text-transform:uppercase;letter-spacing:0.5px;">&#x1F4E3; Share This Link</p>
                        <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                            Any female friend who signs up before <strong>October 23, 2026</strong> automatically gets <strong>2 months FREE Premium</strong> &#x2014; no payment needed!
                        </p>
                        <div style="background:#fdf4ff;border-radius:10px;padding:12px 16px;margin-top:14px;word-break:break-all;">
                            <code style="color:#7e22ce;font-size:14px;font-weight:700;">{referral_link}</code>
                        </div>
                    </div>
                    <div style="text-align:center;">
                        <a href="{referral_link}" style="background:linear-gradient(135deg,#a855f7 0%,#7e22ce 100%);color:white;padding:14px 32px;text-decoration:none;border-radius:50px;font-weight:900;font-size:15px;display:inline-block;box-shadow:0 6px 20px rgba(168,85,247,0.4);">
                            &#x1F4F2; Share Find Your Match
                        </a>
                    </div>
                </div>

                <!-- ===== OFFER DEADLINE NOTICE ===== -->
                <div style="margin:0 25px 30px;background:#fffbeb;border:1px solid #fef3c7;border-left:5px solid #f59e0b;border-radius:14px;padding:18px 20px;">
                    <p style="margin:0;color:#92400e;font-size:14px;line-height:1.6;">
                        <strong>&#x23F0; Offer Deadline:</strong> The free access promotion ends on
                        <strong>October 23, 2026</strong>. After that, normal pricing applies.
                        Log in and use your free access before it expires!
                    </p>
                </div>

                <!-- ===== FOOTER ===== -->
                <div style="background:#fafafa;padding:28px 30px;text-align:center;border-top:1px solid #eee;">
                    <p style="margin:0 0 8px;font-size:13px;font-weight:900;color:#720000;letter-spacing:0.5px;">&#x1F496; FIND YOUR MATCH</p>
                    <p style="margin:0 0 6px;font-size:12px;color:#aaa;">findyourmatch.co.ke &mdash; Kenya's Campus Dating Community</p>
                    <p style="margin:0;font-size:11px;color:#ccc;">&copy; {datetime.now().year} Find Your Match. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)



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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>

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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>

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
                        &copy; {datetime.now().year} Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>

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

                    </p>
                </div>
                
                <!-- FOOTER -->
                <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="margin: 0 0 5px; font-size: 12px; color: #94a3b8; font-weight: 800;">FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .</p>
                    <p style="margin: 0; font-size: 11px; color: #cbd5e1;">&copy; {datetime.now().year} Delstarford Works.</p>
                </div>
            </div>
        </body>
        </html>
    """)
    
    return _send_email(recipient_email, subject, body_html)


def send_manager_welcome_email(recipient_email, recipient_name, institution, password):
    """Sends a welcome email to a newly added Campus Manager."""
    subject = "Welcome to the FIND YOUR MATCH Campus Manager Team! 🚀"
    
    text_content = textwrap.dedent(f"""\
        Hello {recipient_name},
        
        Welcome to the team! You have been added as a Campus Manager for {institution}.
        
        Here are your login credentials:
        Email: {recipient_email}
        Temporary Password: {password}
        
        Please log in to your Manager Dashboard and change your password immediately.
        
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
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <h2 style="color: #720000; margin-top: 0; font-size: 26px; font-weight: 950; text-align: center; letter-spacing: -1px;">Welcome to the Team, {recipient_name}! 🚀</h2>
                <p style="color: #555; font-size: 16px; line-height: 1.6; text-align: center; font-weight: 500; margin-bottom: 30px;">
                    You have been officially added as a Campus Manager for <strong>{institution}</strong>!
                </p>
                <div style="background: #FFF5F6; border: 1px solid #FFD6DD; border-radius: 16px; padding: 20px; margin-bottom: 25px; text-align: left;">
                    <p style="margin: 4px 0; font-size: 15px;"><strong>Email:</strong> {recipient_email}</p>
                    <p style="margin: 4px 0; font-size: 15px;"><strong>Temporary Password:</strong> {password}</p>
                </div>
                <p style="color: #333; font-size: 15px; line-height: 1.6; text-align: center;">
                    Please log in to your Manager Dashboard and change your password immediately for security.
                </p>
                <div style="text-align: center; margin-top: 20px;">
                    <a href="{os.getenv('BASE_URL', 'https://match-ai.onrender.com')}/manager_portal" style="background: linear-gradient(135deg, #E60026 0%, #720000 100%); color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: 900; display: inline-block;">
                        Login to Dashboard
                    </a>
                </div>
                <p style="color: #888; font-size: 14px; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; text-align: center;">
                    <strong>The {SENDER_NAME_DEFAULT} Team</strong>
                </p>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content)


def send_survey_campaign_email(email, name):
    """
    Sends an email inviting users to participate in the feedback survey
    in exchange for 1 week of free Premium access.
    """
    try:
        first_name = name.split(' ')[0] if name else "there"
        subject = "Help Us Improve & Get 1 Week of FREE Premium! 🎁"
        
        text_content = f"""
        Hi {first_name},

        We want to make Find Your Match better for you! 
        Take our quick 2-minute feedback survey and as a thank you, we'll give you 1 Week of FREE Premium access.

        Complete the survey here: {os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/survey

        Whether you want to suggest new features, report an issue, or just tell us what you love, we are listening.

        Best,
        The Find Your Match Team
        """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 500px; margin: 40px auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <!-- HEADER -->
                <div style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%); padding: 30px; text-align: center;">
                    <div style="font-size: 40px; margin-bottom: 10px;">&#x1F381;</div>
                    <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">1 Week Free Premium!</h1>
                </div>
                
                <!-- BODY -->
                <div style="padding: 40px 30px;">
                    <h2 style="margin: 0 0 15px; color: #0F172A; font-size: 20px; font-weight: 800;">Hi {first_name},</h2>
                    <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 20px;">
                        We are constantly working to make Find Your Match better for our campus community, and we need your help!
                    </p>
                    
                    <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                        Take our quick 2-minute feedback survey, and as a thank you, your account will instantly be credited with <strong>1 Week of FREE Premium access</strong> (or a 1-week extension if you're already subscribed).
                    </p>
                    
                    <div style="text-align: center; margin-top: 20px;">
                        <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/survey" style="background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%); color: white; padding: 14px 30px; text-decoration: none; border-radius: 12px; font-size: 16px; font-weight: 900; display: inline-block; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.4);">
                            Take Survey &amp; Claim Reward
                        </a>
                    </div>
                </div>
                
                <!-- FOOTER -->
                <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="margin: 0 0 5px; font-size: 12px; color: #94a3b8; font-weight: 800;">FIND YOUR MATCH</p>
                    <p style="margin: 0; font-size: 11px; color: #ccc;">findyourmatch.co.ke</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return _send_email(email, subject, text_content, html_content)
    except Exception as e:
        logger.error(f"Failed to send survey campaign email to {email}: {e}")
        return False

        
        text_content = f"""
        Hi {first_name},

        We want to make Find Your Match AI better for you! 
        Take our quick 2-minute feedback survey and as a thank you, we'll give you 1 Week of FREE Premium access.

        Complete the survey here: {os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/survey

        Whether you want to suggest new features, report an issue, or just tell us what you love, we are listening.

        Best,
        The Find Your Match AI Team
        """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
            <div style="max-width: 500px; margin: 40px auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
                <!-- HEADER -->
                <div style="background: linear-gradient(135deg, #10b981 0%, #34d399 100%); padding: 30px; text-align: center;">
                    <div style="font-size: 40px; margin-bottom: 10px;">🎁</div>
                    <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">1 Week Free Premium!</h1>
                </div>
                
                <!-- BODY -->
                <div style="padding: 40px 30px;">
                    <h2 style="margin: 0 0 15px; color: #0F172A; font-size: 20px; font-weight: 800;">Hi {first_name},</h2>
                    <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 20px;">
                        We are constantly working to make Find Your Match AI better for our campus community, and we need your help!
                    </p>
                    
                    <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                        Take our quick 2-minute feedback survey, and as a thank you, your account will instantly be credited with <strong>1 Week of FREE Premium access</strong> (or a 1-week extension if you're already subscribed).
                    </p>
                    
                    <div style="text-align: center; margin-top: 20px;">
                        <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/survey" style="background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%); color: white; padding: 14px 30px; text-decoration: none; border-radius: 12px; font-size: 16px; font-weight: 900; display: inline-block; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.4);">
                            Take Survey & Claim Reward
                        </a>
                    </div>
                </div>
                
                <!-- FOOTER -->
                <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="margin: 0 0 5px; font-size: 12px; color: #94a3b8; font-weight: 800;">FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Live through Artificial Intelligence .</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return _send_email(email, subject, text_content, html_content)
    except Exception as e:
        logger.error(f"Failed to send survey campaign email to {email}: {e}")
        return False

def send_manager_otp_email(recipient_email, otp_code):
    """
    Sends a formatted HTML verification email for manager login.
    """
    subject = "Campus Manager Portal - Login OTP"
    headline = "Manager Portal Verification 🏢"
    message = "Use the verification code below to access the campus manager portal. This code expires in 10 minutes."
    
    text_content = f"{headline}\n\n{message}\n\nYour code is: {otp_code}\n\nPlease do not share this code."
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
            <div style="text-align: center; padding-bottom: 20px; border-bottom: 2px solid #f0f0f0;">
                <h2 style="color: #333333; margin: 0;">{headline}</h2>
            </div>
            <div style="padding: 20px 0; color: #555555; line-height: 1.6; font-size: 16px;">
                <p>{message}</p>
                <div style="text-align: center; margin: 30px 0;">
                    <span style="display: inline-block; padding: 15px 30px; font-size: 24px; font-weight: bold; color: #E60026; background-color: #FEF2F4; border-radius: 8px; letter-spacing: 5px;">
                        {otp_code}
                    </span>
                </div>
                <p style="font-size: 14px; color: #888888; text-align: center;">If you didn't request this code, please ignore this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return _send_email(recipient_email, subject, text_content, html_content, sender_name="FYM Manager System")

def send_apology_email(email, user_name=""):
    """
    Sends an apology email regarding the recent login system interruption.
    """
    subject = "Important Update: We've Fixed the Login Issue (And We Are Sorry!)"
    
    first_name = user_name.split()[0] if user_name else "there"
    
    text_content = f"""
    Hi {first_name},

    We are sincerely sorry for the inconvenience caused by the recent system login interruption. 
    You are the boss, and you deserve a flawless experience. We want to assure you that such an interruption will never happen again.
    
    Our engineering team has completely resolved the issue. Please log in to your account and confirm that everything is working perfectly for you.
    
    If you ever experience any inconveniences in the future, please don't hesitate to send a support ticket. You are in control, and we are always here to serve you.
    
    We wish you a very happy weekend and a beautiful relationship journey ahead. Your perfect matches are waiting for you!
    
    Best regards,
    The Find Your Match AI Team
    """
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <div style="max-width: 500px; margin: 40px auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
            <!-- HEADER -->
            <div style="background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%); padding: 30px; text-align: center;">
                <div style="font-size: 40px; margin-bottom: 10px;">🙏</div>
                <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: 900; letter-spacing: -0.5px;">We Are Sincerely Sorry</h1>
            </div>
            
            <!-- BODY -->
            <div style="padding: 40px 30px;">
                <h2 style="margin: 0 0 15px; color: #0F172A; font-size: 20px; font-weight: 800;">Hi {first_name},</h2>
                <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 20px;">
                    We are deeply sorry for the inconvenience caused by the recent system login interruption. As a valued member, <strong>you are the boss</strong>, and you deserve a completely flawless experience. 
                </p>
                
                <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 20px;">
                    We want to personally assure you that our engineering team has completely resolved this issue, and an interruption like this will <strong>never happen again</strong>.
                </p>
                
                <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                    Please log in at your convenience to confirm that everything is working perfectly. If you ever experience any issues, please don't hesitate to open a support ticket. You are always in control, and we are here to serve you.
                </p>
                
                <div style="text-align: center; margin-top: 20px; margin-bottom: 30px;">
                    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/login" style="background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%); color: white; padding: 14px 30px; text-decoration: none; border-radius: 12px; font-size: 16px; font-weight: 900; display: inline-block; box-shadow: 0 4px 15px rgba(14, 165, 233, 0.4);">
                        Log In Now
                    </a>
                </div>
                
                <div style="background-color: #fdf2f8; padding: 20px; border-radius: 12px; border-left: 4px solid #db2777;">
                    <p style="margin: 0; color: #9d174d; font-size: 15px; line-height: 1.5; font-weight: 600;">
                        We wish you a very happy weekend and a beautiful relationship journey ahead. Your perfect matches are waiting for you! ❤️
                    </p>
                </div>
            </div>
            
            <!-- FOOTER -->
            <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0 0 5px; font-size: 12px; color: #94a3b8; font-weight: 800;">FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Lives through Artificial Intelligence .</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        return _send_email(email, subject, text_content, html_content)
    except Exception as e:
        logger.error(f"Failed to send apology email to {email}: {e}")
        return False

def send_system_update_email(email, user_name=""):
    """
    Alerts users of the new Group Chat feature and apologizes for web application issues.
    """
    subject = "🚀 New Feature: Group Chats + Important System Update!"
    
    first_name = user_name.split()[0] if user_name else "there"
    
    text_content = f"""
    Hi {first_name},

    We have some exciting news! We've just added a brand-new Group Chat feature to the platform! 
    You can now join groups, chat with multiple users, shoot your shot, and run vibe checks all in one place.

    Important Update:
    We are aware of the recent problems with our web application. Please know that our engineering team is working around the clock to solve it, and the system will be fully up and running soon.

    We sincerely appreciate your patience and promise you an amazing experience once everything is restored.

    Best regards,
    The Find Your Match AI Team
    """
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
        <div style="max-width: 500px; margin: 40px auto; background: #ffffff; border-radius: 20px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
            <!-- LOGO HEADER -->
            <div style="text-align: center; padding: 20px 0; background-color: #ffffff; border-bottom: 1px solid #f0f0f0;">
                <img src="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/static/img/icon-512.png" alt="Find Your Match" style="width: 100%; max-width: 250px; height: auto; display: block; margin: 0 auto;">
            </div>
            <!-- HEADER -->
            <div style="background: linear-gradient(135deg, #0ea5e9 0%, #38bdf8 100%); padding: 30px; text-align: center;">
                <div style="font-size: 40px; margin-bottom: 10px;">💬</div>
                <h1 style="margin: 0; color: #ffffff; font-size: 22px; font-weight: 900; letter-spacing: -0.5px;">New Group Chats & Updates</h1>
            </div>
            
            <!-- BODY -->
            <div style="padding: 40px 30px;">
                <h2 style="margin: 0 0 15px; color: #0F172A; font-size: 20px; font-weight: 800;">Hi {first_name},</h2>
                <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 20px;">
                    We have some exciting news! We've just added a brand-new <strong>Group Chat</strong> feature to the platform! 
                    You can now join groups, chat with multiple users, shoot your shot, and run vibe checks all in one place.
                </p>
                
                <div style="background-color: #fdf2f8; padding: 20px; border-radius: 12px; border-left: 4px solid #db2777; margin-bottom: 25px;">
                    <strong style="color: #9d174d; font-size: 16px;">System Notice</strong>
                    <p style="margin: 10px 0 0; color: #9d174d; font-size: 14px; line-height: 1.5; font-weight: 500;">
                        We are fully aware of the recent problems with our web application. Please know that our engineering team is <strong>working around the clock</strong> to solve it, and the system will be fully up and running soon.
                    </p>
                </div>
                
                <p style="color: #475569; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                    We sincerely appreciate your patience and promise you an amazing experience once everything is fully restored. You are the boss, and we are here to serve you!
                </p>
                
                <div style="text-align: center; margin-top: 20px; margin-bottom: 20px;">
                    <a href="{os.getenv('BASE_URL', 'https://findyourmatch.co.ke')}/groups" style="background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%); color: white; padding: 14px 30px; text-decoration: none; border-radius: 12px; font-size: 16px; font-weight: 900; display: inline-block; box-shadow: 0 4px 15px rgba(225, 29, 72, 0.4);">
                        Check out Group Chats
                    </a>
                </div>
            </div>
            <!-- FOOTER -->
            <div style="background: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0 0 5px; font-size: 12px; color: #94a3b8; font-weight: 800;">FIND YOUR MATCH AI | Powered by DELSTARFORD WORKS , Transforming Lives through Artificial Intelligence .</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        return _send_email(email, subject, text_content, html_content)
    except Exception as e:
        logger.error(f"Failed to send system update email to {email}: {e}")
        return False


# ==========================================
# SPONSOR SYSTEM EMAILS (v2)
# ==========================================

def send_sponsor_welcome_email(recipient_email: str, recipient_name: str) -> bool:
    """Sent to a new sponsor after their 1000 KSH registration payment is confirmed."""
    subject = "💖 Welcome to FindYourMatch Sponsors — You're In!"

    text_content = textwrap.dedent(f"""\
        Welcome, {recipient_name}!

        Your sponsor account on FindYourMatch is now active.
        Your profile is under review and will be verified shortly.

        You can now:
        - Complete your profile and upload a photo
        - Browse student profiles
        - Send connection requests to students

        Log in at: https://findyourmatch.co.ke/sponsor/login

        Wishing you all the best,
        — The FindYourMatch Team
    """)

    base_url = os.getenv("BASE_URL", "https://findyourmatch.co.ke")
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="margin:0;padding:20px;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
            <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.07);">
                <!-- Logo -->
                <div style="text-align:center;padding:20px 0;border-bottom:1px solid #f0f0f0;">
                    <img src="{base_url}/static/img/icon-512.png" alt="FindYourMatch" style="max-width:200px;height:auto;">
                </div>
                <!-- Hero -->
                <div style="background:linear-gradient(135deg,#720000,#e60026);padding:40px 30px;text-align:center;color:white;">
                    <div style="font-size:48px;margin-bottom:12px;">🌟</div>
                    <h1 style="margin:0 0 8px;font-size:26px;font-weight:900;">Welcome, {recipient_name}!</h1>
                    <p style="margin:0;font-size:15px;opacity:0.9;">Your sponsor account is now active on FindYourMatch</p>
                </div>
                <!-- Body -->
                <div style="padding:35px 30px;">
                    <p style="font-size:16px;color:#334155;line-height:1.7;margin-top:0;">
                        Congratulations! Your registration is complete and your profile is now live.
                        Our team will verify your account shortly and you'll be discoverable by students across Kenya.
                    </p>
                    <div style="background:#fef2f2;border-radius:12px;padding:20px;border:1px solid #fecaca;margin:25px 0;">
                        <h3 style="color:#720000;margin:0 0 12px;font-size:16px;">✅ What you can do now:</h3>
                        <ul style="margin:0;padding-left:20px;color:#334155;font-size:14px;line-height:2;">
                            <li>Complete your profile and upload your photo</li>
                            <li>Browse student profiles looking for sponsors</li>
                            <li>Send connection requests and start conversations</li>
                            <li>Receive weekly match suggestions via email</li>
                        </ul>
                    </div>
                    <div style="text-align:center;margin-top:30px;">
                        <a href="{base_url}/sponsor/login"
                           style="display:inline-block;padding:15px 35px;background:linear-gradient(135deg,#720000,#e60026);
                                  color:white;text-decoration:none;border-radius:30px;font-size:15px;font-weight:bold;
                                  box-shadow:0 4px 15px rgba(230,0,38,0.3);">
                            💖 Go to My Sponsor Dashboard
                        </a>
                    </div>
                    <p style="margin-top:30px;font-size:13px;color:#94a3b8;text-align:center;font-style:italic;">
                        May you find exactly what you're looking for. 🌹
                    </p>
                </div>
                <!-- Footer -->
                <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:12px;">
                    &copy; {datetime.now().year} FindYourMatch.co.ke | Powered by DELSTARFORD WORKS
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content, sender_name="FindYourMatch")


def send_sponsor_room_welcome_email(recipient_email: str, recipient_name: str, is_free: bool = False) -> bool:
    """Sent to a student after gaining Sponsors Room access (paid or free)."""
    subject = "🏠 You're In — Welcome to the FindYourMatch Sponsors Room!"
    access_note = "as a complimentary benefit" if is_free else "for the next 30 days"

    text_content = textwrap.dedent(f"""\
        Hi {recipient_name}!

        You now have access to the FindYourMatch Sponsors Room {access_note}.

        Inside you'll find sponsor profiles — people outside campus who are interested
        in connecting with students like you. Browse their profiles and say hello!

        Visit: https://findyourmatch.co.ke/sponsors-room

        Have a blessed day,
        — The FindYourMatch Team
    """)

    base_url = os.getenv("BASE_URL", "https://findyourmatch.co.ke")
    html_content = textwrap.dedent(f"""\
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
        <body style="margin:0;padding:20px;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
            <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:20px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,0.07);">
                <div style="text-align:center;padding:20px 0;border-bottom:1px solid #f0f0f0;">
                    <img src="{base_url}/static/img/icon-512.png" alt="FindYourMatch" style="max-width:200px;height:auto;">
                </div>
                <div style="background:linear-gradient(135deg,#7c3aed,#a855f7);padding:40px 30px;text-align:center;color:white;">
                    <div style="font-size:48px;margin-bottom:12px;">🏠✨</div>
                    <h1 style="margin:0 0 8px;font-size:26px;font-weight:900;">You're In, {recipient_name}!</h1>
                    <p style="margin:0;font-size:15px;opacity:0.9;">The Sponsors Room is now unlocked for you {access_note}</p>
                </div>
                <div style="padding:35px 30px;">
                    <p style="font-size:16px;color:#334155;line-height:1.7;margin-top:0;">
                        Welcome to the <strong>FindYourMatch Sponsors Room</strong> — an exclusive space where students
                        connect with sponsors who are genuinely interested in meaningful relationships.
                    </p>
                    <div style="background:#f5f3ff;border-radius:12px;padding:20px;border:1px solid #ddd6fe;margin:25px 0;">
                        <h3 style="color:#7c3aed;margin:0 0 12px;font-size:16px;">🎯 Inside the Sponsors Room:</h3>
                        <ul style="margin:0;padding-left:20px;color:#334155;font-size:14px;line-height:2;">
                            <li>Browse verified sponsor profiles</li>
                            <li>See compatibility scores</li>
                            <li>Send connection requests</li>
                            <li>Chat directly with sponsors</li>
                        </ul>
                    </div>
                    <div style="text-align:center;margin-top:30px;">
                        <a href="{base_url}/sponsors-room"
                           style="display:inline-block;padding:15px 35px;background:linear-gradient(135deg,#7c3aed,#a855f7);
                                  color:white;text-decoration:none;border-radius:30px;font-size:15px;font-weight:bold;
                                  box-shadow:0 4px 15px rgba(124,58,237,0.3);">
                            🚀 Enter the Sponsors Room
                        </a>
                    </div>
                    <p style="margin-top:30px;font-size:13px;color:#94a3b8;text-align:center;font-style:italic;">
                        Your perfect match is waiting. Have a blessed day! 💖
                    </p>
                </div>
                <div style="background:#f8fafc;padding:20px;text-align:center;border-top:1px solid #e2e8f0;color:#94a3b8;font-size:12px;">
                    &copy; {datetime.now().year} FindYourMatch.co.ke | Powered by DELSTARFORD WORKS
                </div>
            </div>
        </body>
        </html>
    """)

    return _send_email(recipient_email, subject, text_content, html_content, sender_name="FindYourMatch")
