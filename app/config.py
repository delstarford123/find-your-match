# config.py
import os

VAPID_PUBLIC_KEY = os.getenv(
    "VAPID_PUBLIC_KEY",
    "BKQCzvEGmGI5a1Ynzx_ANsriL6EKKL9gP-ncDrXhbR3Uqt9tqu94hLmzWafWx0ROucd6K8tJrsu3skzFwP2uIUk"
)
_default_pem = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'private_key.pem'))
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", _default_pem)

mail_contact = os.getenv("MAIL_USERNAME", "delstarfordisaiah@gmail.com")
VAPID_CLAIMS = {
    "sub": f"mailto:{mail_contact}"
}