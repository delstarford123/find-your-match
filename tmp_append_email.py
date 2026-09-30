import os

def append_func():
    path = r'c:\Users\Delstaford\Desktop\mmust-dating-ai\mmust-dating-ai\app\email_service.py'
    with open(path, 'a', encoding='utf-8') as f:
        f.write('''

def send_manager_otp_email(recipient_email, otp_code):
    """
    Sends a formatted HTML verification email for manager login.
    """
    subject = "Campus Manager Portal - Login OTP"
    headline = "Manager Portal Verification 🏢"
    message = "Use the verification code below to access the campus manager portal. This code expires in 10 minutes."
    
    text_content = f"{headline}\\n\\n{message}\\n\\nYour code is: {otp_code}\\n\\nPlease do not share this code."
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
        <div style="max-width: 600px; margin: auto; background-color: #ffffff; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
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
''')

if __name__ == "__main__":
    append_func()
