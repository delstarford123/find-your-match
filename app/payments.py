import os
import requests
import base64
import logging
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)

# ==========================================
# DARAJA API CREDENTIALS
# We pull these from your .env file for security. 
# The sandbox keys are left here as fallbacks for testing.
# ==========================================
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
BUSINESS_SHORTCODE = os.getenv("MPESA_SHORTCODE") 
PASSKEY = os.getenv("MPESA_PASSKEY")

# Toggle between 'sandbox' and 'production' in your .env file
ENVIRONMENT = os.getenv("MPESA_ENV", "sandbox").lower()

if ENVIRONMENT == "production":
    BASE_URL = "https://api.safaricom.co.ke"
else:
    BASE_URL = "https://sandbox.safaricom.co.ke"

OAUTH_URL = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"
STK_QUERY_URL = f"{BASE_URL}/mpesa/stkpushquery/v1/query"

def get_access_token():
    """Generates the temporary OAuth token required by Safaricom."""
    try:
        response = requests.get(OAUTH_URL, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=10)
        response.raise_for_status()
        return response.json().get('access_token')
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to get M-Pesa access token: {e}")
        return None

def generate_password(timestamp):
    """Combines Shortcode, Passkey, and Timestamp into a Base64 string."""
    data_to_encode = f"{BUSINESS_SHORTCODE}{PASSKEY}{timestamp}"
    return base64.b64encode(data_to_encode.encode('utf-8')).decode('utf-8')

def initiate_stk_push(phone_number, amount, account_reference, callback_url, transaction_desc="MMUST Subscription"):
    """
    Triggers the PIN prompt on the user's phone.
    Returns a dictionary containing the 'CheckoutRequestID' which you use to track the payment.
    """
    token = get_access_token()
    if not token:
        return {"error": "Failed to authenticate with M-Pesa."}

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(timestamp)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": BUSINESS_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone_number,
        "PartyB": BUSINESS_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": callback_url,
        "AccountReference": str(account_reference)[:12], # Max 12 chars allowed by Safaricom
        "TransactionDesc": transaction_desc[:13] # Max 13 chars allowed
    }

    try:
        response = requests.post(STK_PUSH_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json() 
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ STK Push Error: {e}")
        if response is not None:
            logger.error(f"Safaricom Response: {response.text}")
        return {"error": str(e)}

def check_payment_status(checkout_request_id):
    """
    ACTIVELY asks Safaricom if a specific transaction was paid successfully.
    Use this if you want your frontend to poll the backend while the user is typing their PIN.
    """
    token = get_access_token()
    if not token:
        return {"error": "Auth failed."}

    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    password = generate_password(timestamp)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "BusinessShortCode": BUSINESS_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id
    }

    try:
        response = requests.post(STK_QUERY_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        # ResultCode 0 means the user entered their PIN and the money was sent successfully
        if data.get('ResultCode') == "0":
            return {"status": "PAID", "data": data}
        # ResultCode 1032 means transaction was canceled by user
        elif data.get('ResultCode') == "1032":
            return {"status": "CANCELED", "data": data}
        else:
            return {"status": "FAILED", "data": data}
            
    except requests.exceptions.RequestException as e:
        # A 400 error usually means the transaction is still pending (user hasn't typed PIN yet)
        return {"status": "PENDING"}