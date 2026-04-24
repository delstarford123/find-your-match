import os
import requests
import base64
import logging
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

# ==========================================
# DARAJA API CREDENTIALS (PRODUCTION)
# ==========================================
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
BUSINESS_SHORTCODE = os.getenv("MPESA_SHORTCODE") 
PASSKEY = os.getenv("MPESA_PASSKEY")

# Hardcoded to the live Safaricom API
BASE_URL = "https://api.safaricom.co.ke"

OAUTH_URL = f"{BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
STK_PUSH_URL = f"{BASE_URL}/mpesa/stkpush/v1/processrequest"
STK_QUERY_URL = f"{BASE_URL}/mpesa/stkpushquery/v1/query"

# === IN-MEMORY TOKEN CACHE ===
_token_cache = {
    "token": None,
    "expires_at": None
}

def validate_credentials():
    """Ensures the server has all required M-Pesa keys before attempting a request."""
    if not all([CONSUMER_KEY, CONSUMER_SECRET, BUSINESS_SHORTCODE, PASSKEY]):
        logger.error("🚨 CRITICAL: Missing one or more M-Pesa Environment Variables!")
        return False
    return True

def format_phone_number(phone: str) -> str:
    """Ensures the phone number is strictly in the 254XXXXXXXXX format."""
    if not phone:
        return ""
        
    phone = ''.join(filter(str.isdigit, str(phone)))
    
    if phone.startswith('0') and len(phone) == 10:
        return '254' + phone[1:]
    if phone.startswith('254') and len(phone) == 12:
        return phone
    if len(phone) == 9:
        return '254' + phone
        
    return phone 

def get_access_token():
    """Generates or retrieves a valid OAuth token required by Safaricom."""
    if not validate_credentials():
        return None

    global _token_cache
    
    # Use cached token if it is still valid for at least another 60 seconds
    if _token_cache["token"] and _token_cache["expires_at"]:
        if datetime.now() < (_token_cache["expires_at"] - timedelta(seconds=60)):
            return _token_cache["token"]

    try:
        response = requests.get(OAUTH_URL, auth=(CONSUMER_KEY, CONSUMER_SECRET), timeout=15)
        response.raise_for_status()
        data = response.json()
        
        _token_cache["token"] = data.get('access_token')
        _token_cache["expires_at"] = datetime.now() + timedelta(seconds=int(data.get('expires_in', 3599)))
        
        return _token_cache["token"]
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to get M-Pesa access token: {e}")
        return None
    except ValueError:
        # Catches cases where Daraja returns a 503 HTML page instead of JSON
        logger.error("❌ Daraja returned a non-JSON response during Auth.")
        return None

def generate_password(timestamp: str) -> str:
    """Combines Shortcode, Passkey, and Timestamp into a Base64 string."""
    data_to_encode = f"{BUSINESS_SHORTCODE}{PASSKEY}{timestamp}"
    return base64.b64encode(data_to_encode.encode('utf-8')).decode('utf-8')

def initiate_stk_push(phone_number, amount, account_reference, callback_url, transaction_desc="MMUST Subscription"):
    """Triggers the PIN prompt on the user's phone."""
    token = get_access_token()
    if not token:
        return {"error": "Failed to authenticate with M-Pesa Servers."}

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
        "AccountReference": str(account_reference)[:12], 
        "TransactionDesc": str(transaction_desc)[:13] 
    }

    try:
        response = requests.post(STK_PUSH_URL, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json() 
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ STK Push Network Error: {e}")
        
        if getattr(e, 'response', None) is not None:
            try:
                safaricom_error = e.response.json()
                error_msg = safaricom_error.get('errorMessage', str(e))
                logger.error(f"Safaricom Exact Response: {error_msg}")
                return {"error": f"Safaricom: {error_msg}"}
            except ValueError:
                # Safaricom sent back HTML instead of JSON
                logger.error(f"Safaricom returned an invalid format: {e.response.text[:200]}")
                return {"error": "Safaricom gateway is currently unstable."}
                
        return {"error": "Network timeout reaching Safaricom."}

def check_payment_status(checkout_request_id):
    """ACTIVELY asks Safaricom if a specific transaction was paid successfully."""
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
        
        result_code = str(data.get('ResultCode'))
        
        if result_code == "0":
            return {"status": "PAID", "data": data}
        elif result_code == "1032":
            return {"status": "CANCELED", "data": data}
        else:
            return {"status": "FAILED", "data": data}
            
    except requests.exceptions.RequestException as e:
        if getattr(e, 'response', None) is not None:
            try:
                error_data = e.response.json()
                # Safaricom returns "Invalid CheckoutRequestID" if the user hasn't put in their PIN yet
                err_msg = error_data.get('errorMessage', '').lower()
                if "invalid" in err_msg or "not found" in err_msg:
                    return {"status": "PENDING"}
            except ValueError:
                pass # Daraja returned HTML
                
        return {"status": "PENDING"}