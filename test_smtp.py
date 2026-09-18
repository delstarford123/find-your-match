import os
import smtplib
from dotenv import load_dotenv

load_dotenv()

smtp_server = os.getenv("MAIL_SERVER", "mail.findyourmatch.co.ke")
smtp_port = int(os.getenv("MAIL_PORT", 465))
sender_email = os.getenv("MAIL_USERNAME", "noreply@findyourmatch.co.ke")
sender_password = os.getenv("MAIL_PASSWORD", "Delstarford123")

print(f"Server: {smtp_server}:{smtp_port}, User: {sender_email}")

try:
    print("Testing SMTP_SSL...")
    with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
        server.set_debuglevel(1)
        server.login(sender_email, sender_password)
        print("SMTP_SSL Login successful!")
except Exception as e:
    print("SMTP_SSL Failed:", e)

try:
    print("\nTesting STARTTLS on port 587...")
    with smtplib.SMTP(smtp_server, 587, timeout=10) as server:
        server.set_debuglevel(1)
        server.starttls()
        server.login(sender_email, sender_password)
        print("STARTTLS Login successful!")
except Exception as e:
    print("STARTTLS Failed:", e)
