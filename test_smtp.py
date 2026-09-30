import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl

smtp_server = "mail.findyourmatch.co.ke"
smtp_port = 465
sender_email = "noreply@findyourmatch.co.ke"
sender_password = "Delstarford123"
recipient = "delstarfordworks@gmail.com" # Just a test email

msg = MIMEMultipart('alternative')
msg['Subject'] = "Test Email"
msg['From'] = f"FIND YOUR MATCH AI <{sender_email}>"
msg['To'] = recipient

body_text = "This is a test."
msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

try:
    context = ssl._create_unverified_context()
    server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10, context=context)
    server.login(sender_email, sender_password)
    server.sendmail(sender_email, recipient, msg.as_string())
    server.quit()
    print("Success")
except Exception as e:
    print(f"Error: {e}")
