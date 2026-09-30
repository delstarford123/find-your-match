import os, sys, time, logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from email_service import send_survey_campaign_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
logger = logging.getLogger("retry_failed")

def retry_failed():
    # These are the emails we could see from your terminal snippet that failed due to DNS/network errors
    failed_emails = [
        ("Brighton", "odhiambobrighton796@gmail.com"),
        ("Martin Muange", "martinmbokamuange@gmail.com"),
        ("JUJU", "adamslyonne4@gmail.com"),
        ("INZAI", "galavubraison@gmail.com"),
        ("Joseph", "phelixsilvia@gmail.com"),
        ("Owala Collins", "owalacollins10@gmail.com"),
        ("Emmanuel webbo kombo", "emmanuelwebbo2006@gmail.com"),
        ("Fred Barasa Fwamba", "barasabara133@gmail.com"),
        ("Barnabas Musoma", "ofumatotoo@gmail.com"),
        ("Peter Ochieng", "odhiambop914@gmail.com"),
        ("Ian Otinga", "i02369641@gmail.com"),
        ("Greg", "lagatkipkalya008@gmail.com"),
        ("FRANK DE GREAT", "francisabuna32@gmail.com"),
        ("Fletooh", "ochielflato@gmail.com"),
        ("Kalito", "kropreuben58@gmail.com"),
        ("Jack Dee", "denceljack72@gmail.com"),
        ("Karis Yusuf", "mluyawajuja@gmail.com"),
        ("Jeremy", "ingosijeremy@gmail.com"),
        ("Mogeka Denis", "mogekadenis092@gmail.com"),
        ("Rick", "omondiderrick247@gmail.com"),
        ("Michael", "mkhaemba503@gmail.com"),
        ("Lee", "leovateadagi76@gmail.com"),
        ("Mendy", "brianmiguna0@gmail.com"),
        ("Okomo Peter", "okomopeter92@gmail.com"),
        ("James Owino", "owinojames756@gmail.com"),
        ("jjj", "jj@gmail.com"),
        ("Kevin Abila", "abilakevin11@gmail.com")
    ]
    
    # If you have the full terminal log, you can paste the rest of the failed emails in this list manually.
    
    logger.info(f"Attempting to retry {len(failed_emails)} failed emails...")
    
    sent = 0
    failed = 0
    for name, email in failed_emails:
        if send_survey_campaign_email(email, name):
            logger.info(f"✅ Sent -> {name} <{email}>")
            sent += 1
        else:
            logger.error(f"❌ FAILED -> {name} <{email}>")
            failed += 1
        time.sleep(1.5)
        
    logger.info(f"Retry Complete! Sent: {sent}, Failed: {failed}")

if __name__ == "__main__":
    retry_failed()
