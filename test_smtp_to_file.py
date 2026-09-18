import os
import smtplib
from dotenv import load_dotenv
import traceback

load_dotenv()

smtp_server = os.getenv("MAIL_SERVER", "mail.findyourmatch.co.ke")
smtp_port = int(os.getenv("MAIL_PORT", 465))
sender_email = os.getenv("MAIL_USERNAME", "noreply@findyourmatch.co.ke")
sender_password = os.getenv("MAIL_PASSWORD", "Delstarford123")

log_output = []
log_output.append(f"Server: {smtp_server}:{smtp_port}, User: {sender_email}")

try:
    log_output.append("Testing SMTP_SSL...")
    with smtplib.SMTP_SSL(smtp_server, 465, timeout=10) as server:
        server.set_debuglevel(1)
        server.login(sender_email, sender_password)
        log_output.append("SMTP_SSL Login successful!")
except Exception as e:
    log_output.append(f"SMTP_SSL Failed: {e}")
    log_output.append(traceback.format_exc())

try:
    log_output.append("\nTesting STARTTLS on port 587...")
    with smtplib.SMTP(smtp_server, 587, timeout=10) as server:
        server.set_debuglevel(1)
        server.starttls()
        server.login(sender_email, sender_password)
        log_output.append("STARTTLS Login successful!")
except Exception as e:
    log_output.append(f"STARTTLS Failed: {e}")
    log_output.append(traceback.format_exc())

with open("smtp_test_log.txt", "w") as f:
    f.write("\n".join(log_output))
