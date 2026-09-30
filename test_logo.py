"""
test_logo.py
Sends a quick test email to verify the logo header injection.
"""

import os, sys, logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import initialize_firebase
from email_service import send_apology_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_mailer")

def run():
    initialize_firebase()
    
    test_email = "delstarfordisaiah@gmail.com"
    logger.info(f"Sending test email to {test_email} to verify the logo header...")
    
    success = send_apology_email(test_email, "Delstarford")
    if success:
        logger.info(f"✅ SUCCESS! Test email sent to {test_email}")
    else:
        logger.error(f"❌ FAILED to send email to {test_email}")

if __name__ == "__main__":
    run()
