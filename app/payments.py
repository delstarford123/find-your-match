import os
import requests
import base64
import logging
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

# ==========================================
# DARAJA API CREDENTIALS
# ==========================================
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
BUSINESS_SHORTCODE = os.getenv("MPESA_SHORTCODE") 
PASSKEY = os.getenv("MPESA_PASSKEY")

ENVIRONMENT = os.getenv("MPESA_ENV", "sandbox").lower()

if ENVIRONMENT == "production":
    BASE_URL = "https://api.safaricom.co.ke"
else:
    BASE_URL = "https://sandbox.safaricom.co.ke"

OAUTH_URL = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"
STK_QUERY_URL = f"{BASE_URL}/mpesa/stkpushquery/v1/query"

# === IN-MEMORY TOKEN CACHE ===
_token_cache = {
    "token": None,
    "expires_at": None
}

def format_phone_number(phone: str) -> str:
    """Ensures the phone number is strictly in the 254XXXXXXXXX format."""
    phone = ''.join(filter(str.isdigit, str(phone)))
    if phone.startswith('0'):
        return '254' + phone[1:]
    if phone.startswith('254'):
        return phone
    if len(phone) == 9:
        return '254' + phone
    return phone

def get_access_token():
    """Generates or retrieves a valid OAuth token required by Safaricom."""
    global _token_cache
    
    # Return cached token if it is still valid (with a 60-second safety buffer)
    if _token_cache["token"] and _token_cache["expires_at"]:
        if datetime.now() < (_token_cache["expires_at"] - timedelta(seconds=60)):
            return _token_cache["token"]

    try:
        response = requests.get(OAUTH_URL, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Cache the new token
        _token_cache["token"] = data.get('access_token')
        # Daraja tokens expire in 3599 seconds
        _token_cache["expires_at"] = datetime.now() + timedelta(seconds=int(data.get('expires_in', 3599)))
        
        return _token_cache["token"]
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to get M-Pesa access token: {e}")
        return None

def generate_password(timestamp: str) -> str:
    """Combines Shortcode, Passkey, and Timestamp into a Base64 string."""
    data_to_encode = f"{BUSINESS_SHORTCODE}{PASSKEY}{timestamp}"
    return base64.b64encode(data_to_encode.encode('utf-8')).decode('utf-8')

def initiate_stk_push(phone_number, amount, account_reference, callback_url, transaction_desc="MMUST Subscription"):
    """
    Triggers the PIN prompt on the user's phone.
    Returns a dictionary containing the 'CheckoutRequestID' to track the payment.
    """
    token = get_access_token()
    if not token:
        return {"error": "Failed to authenticate with M-Pesa."}

    formatted_phone = format_phone_number(phone_number)
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
        "PartyA": formatted_phone,
        "PartyB": BUSINESS_SHORTCODE,
        "PhoneNumber": formatted_phone,
        "CallBackURL": callback_url,
        "AccountReference": str(account_reference)[:12], # Max 12 chars
        "TransactionDesc": str(transaction_desc)[:13] # Max 13 chars
    }

    try:
        response = requests.post(STK_PUSH_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json() 
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ STK Push Error: {e}")
        # FIX: Use e.response to prevent UnboundLocalError if the connection drops
        if e.response is not None:
            logger.error(f"Safaricom Response: {e.response.text}")
        return {"error": str(e)}

def check_payment_status(checkout_request_id):
    """
    ACTIVELY asks Safaricom if a specific transaction was paid successfully.
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
        
        # Safaricom returns ResultCode as a string or int depending on the specific state
        result_code = str(data.get('ResultCode'))
        
        if result_code == "0":
            return {"status": "PAID", "data": data}
        elif result_code == "1032":
            return {"status": "CANCELED", "data": data}
        else:
            return {"status": "FAILED", "data": data}
            
    except requests.exceptions.RequestException as e:
        # A 400 error from Daraja Query usually means the user hasn't entered their PIN yet
        return {"status": "PENDING"}