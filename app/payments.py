import os
import re
import requests
import base64
import logging
from datetime import datetime, timedelta

# Configure logging
logger = logging.getLogger(__name__)

# ==========================================
# DARAJA API CREDENTIALS (PRODUCTION)
# ==========================================
CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY") or os.getenv("CONSUMER_KEY") or "OgkAKD4soo5xGVEegeGPvWS9HK3QuRgZYGQXnKmDxVTxnMDG"
CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET") or os.getenv("CONSUMER_SECRET") or "LXgsZGYdl6kpunxzGuAw4Fi3JK7FtTLqbCK9JZjI6VDR6e93n5mmW8gFKUORhuQQ"
BUSINESS_SHORTCODE = os.getenv("BUSINESS_SHORT_CODE") or os.getenv("MPESA_SHORTCODE") or "4050545"
PASSKEY = os.getenv("MPESA_PASSKEY") or os.getenv("PASSKEY") or "f2d5541751a9649a49971680017613ecec69eb7bd886bda8bfb5d07c5d1c2d1f"

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
    """
    Asks Safaricom if a specific transaction was paid.

    Safaricom Result Codes:
      0    = SUCCESS (PAID)
      1    = Insufficient funds → definitive FAILED
      1032 = User cancelled → definitive CANCELED
      1037 = DS timeout / user unreachable → still PENDING
      2001 = Wrong PIN entered → still PENDING (user may retry)
      17   = Request still being processed → PENDING
      None / missing = query came too early → PENDING
    """
    token = get_access_token()
    if not token:
        return {"status": "PENDING", "error": "Auth failed."}

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

        result_code = data.get('ResultCode')

        # Safaricom may return None or empty string while still processing
        if result_code is None or result_code == '':
            return {"status": "PENDING", "data": data}

        result_code = str(result_code)

        if result_code == "0":
            return {"status": "PAID", "data": data}

        # Only these two codes are DEFINITIVE failures:
        # 1032 = user explicitly pressed 'Cancel' on their phone
        # 1    = genuinely insufficient M-Pesa balance
        elif result_code == "1032":
            return {"status": "CANCELED", "data": data}
        elif result_code == "1":
            return {"status": "FAILED", "data": data, "reason": "Insufficient M-Pesa balance."}

        # All other codes (1037, 2001, 17, etc.) mean
        # Safaricom is still processing — treat as PENDING
        else:
            logger.info(f"STK Query: ambiguous code {result_code} — treating as PENDING")
            return {"status": "PENDING", "data": data}

    except requests.exceptions.RequestException as e:
        if getattr(e, 'response', None) is not None:
            try:
                error_data = e.response.json()
                err_msg = error_data.get('errorMessage', '').lower()
                # "The transaction is being processed" → PENDING
                # "Invalid CheckoutRequestID" → PENDING (queried too fast)
                # Any Safaricom error during processing → PENDING
                logger.info(f"STK Query HTTP error: {err_msg[:80]}")
            except ValueError:
                pass  # Daraja returned HTML instead of JSON

        # Any HTTP error from Safaricom = still processing
        return {"status": "PENDING"}


# ==========================================
# M-PESA B2C PAYOUT SERVICE (AUTOMATED DISBURSALS)
# ==========================================
def initiate_b2c_payout(
    phone_number: str,
    amount: float or int,
    command_id: str = "BusinessPayment",
    remarks: str = "FindYourMatch Payout",
    occasion: str = "Disbursal"
):
    """
    Dispatches an automated B2C payout from Shortcode 4050545 to an individual M-Pesa phone number.
    Supports:
    - command_id="BusinessPayment" (for 2-minute event organizer ticket payouts)
    - command_id="SalaryPayment" (for monthly manager & ambassador salary on the 31st)
    - command_id="PromotionPayment"
    """
    token = get_access_token()
    if not token:
        logger.error("❌ B2C Payout failed: Could not obtain M-Pesa access token.")
        return {"success": False, "error": "Failed to authenticate with M-Pesa."}

    initiator = os.getenv("DARAJA_INITIATOR_NAME") or "Delstarford Api"
    credential = os.getenv("DARAJA_SECURITY_CREDENTIAL") or "fwrS8i2o7+s/XdCz+jl05zQyQgsOv/y6o4tGRETOMqk/3mccnywYx+YngcZgxOWicaEAqzi0U7UoTak83d7QeSJ+F87HER2077r00aB90sLxxZ8/JDoJWNPf6a4xl1Ovd4FesrqfIN6HZcaCfTZU+1gx68vq6cpuKijr6SJ1aHOeCE+tqEbQs2pEllQmb+AefNg+PH2A2ElkBjjKKfMNoEw6GixZeRVewQFloDA2Ymf2Fp67zbvXlMJAIScHViS8h4yNUEtsSwODv1F7TkqbSfNtrMDJ4AilJ3kzXx0rSd8NWnSWZ0pVQOb91qJOhKnvzbm2IEIq+dk9Kw5FtIe07w=="
    shortcode = os.getenv("BUSINESS_SHORT_CODE") or os.getenv("MPESA_SHORTCODE") or "4050545"
    timeout_url = os.getenv("DARAJA_B2C_TIMEOUT_URL") or "https://www.findyourmatch.co.ke/mpesa/b2c/timeout"
    result_url = os.getenv("DARAJA_B2C_RESULT_URL") or "https://www.findyourmatch.co.ke/mpesa/b2c/result"

    if not credential:
        logger.error("❌ B2C Payout failed: Missing DARAJA_SECURITY_CREDENTIAL in environment.")
        return {"success": False, "error": "Missing Daraja security credential."}

    formatted_phone = format_phone_number(phone_number)
    if not formatted_phone or len(formatted_phone) != 12 or not formatted_phone.startswith("254"):
        return {"success": False, "error": f"Invalid recipient phone number: '{phone_number}' (Must be 254XXXXXXXXX)."}

    try:
        clean_amount = int(round(float(amount)))
    except (ValueError, TypeError):
        return {"success": False, "error": f"Invalid payout amount: {amount}"}

    if clean_amount <= 0:
        return {"success": False, "error": "Payout amount must be greater than zero."}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Safaricom Daraja B2C strictly accepts alphanumeric and spaces only, max 20 characters
    clean_remarks = re.sub(r'[^a-zA-Z0-9 ]', '', str(remarks)).strip()[:20] or "Ticket Payout"
    clean_occasion = re.sub(r'[^a-zA-Z0-9 ]', '', str(occasion)).strip()[:20] or "TicketPayout"

    payload = {
        "InitiatorName": initiator,
        "SecurityCredential": credential,
        "CommandID": command_id,
        "Amount": clean_amount,
        "PartyA": shortcode,
        "PartyB": formatted_phone,
        "Remarks": clean_remarks,
        "QueueTimeOutURL": timeout_url,
        "ResultURL": result_url,
        "Occasion": clean_occasion
    }

    # Try v3 first, then v1
    urls = [
        f"{BASE_URL}/mpesa/b2c/v3/paymentrequest",
        f"{BASE_URL}/mpesa/b2c/v1/paymentrequest"
    ]

    last_error = None
    for b2c_url in urls:
        try:
            logger.info(f"📤 Sending B2C Payout: KES {clean_amount} to {formatted_phone} via {b2c_url}...")
            res = requests.post(b2c_url, json=payload, headers=headers, timeout=25)
            data = res.json()
            
            if res.status_code in [200, 201] and (data.get('ResponseCode') == '0' or 'ConversationID' in data):
                logger.info(f"✅ B2C Disbursed Successfully: ConversationID={data.get('ConversationID')}")
                return {
                    "success": True,
                    "ConversationID": data.get('ConversationID'),
                    "OriginatorConversationID": data.get('OriginatorConversationID'),
                    "ResponseDescription": data.get('ResponseDescription', 'Accepted'),
                    "data": data
                }
            else:
                err_msg = data.get('errorMessage') or data.get('ResponseDescription') or str(data)
                logger.warning(f"⚠️ B2C from {b2c_url}: {err_msg}")
                last_error = err_msg
        except Exception as e:
            logger.error(f"❌ B2C request exception for {b2c_url}: {e}")
            last_error = str(e)

    return {"success": False, "error": last_error or "B2C request failed."}


# ==========================================
# M-PESA B2B PAYOUT SERVICE (BUSINESS TRANSFERS)
# ==========================================
def initiate_b2b_payout(
    receiver_shortcode: str,
    amount: float or int,
    command_id: str = "BusinessPayBill",
    remarks: str = "Event Ticket Payout",
    account_reference: str = "TicketCash"
):
    """
    Dispatches an automated B2B transfer from Shortcode 4050545 to an external Till or Paybill.
    Supports:
    - command_id="BusinessPayBill" (to Paybill)
    - command_id="BusinessBuyGoods" (to Till Number)
    """
    token = get_access_token()
    if not token:
        logger.error("❌ B2B Payout failed: Could not obtain M-Pesa access token.")
        return {"success": False, "error": "Failed to authenticate with M-Pesa."}

    initiator = os.getenv("DARAJA_INITIATOR_NAME") or "Delstarford Api"
    credential = os.getenv("DARAJA_SECURITY_CREDENTIAL") or "fwrS8i2o7+s/XdCz+jl05zQyQgsOv/y6o4tGRETOMqk/3mccnywYx+YngcZgxOWicaEAqzi0U7UoTak83d7QeSJ+F87HER2077r00aB90sLxxZ8/JDoJWNPf6a4xl1Ovd4FesrqfIN6HZcaCfTZU+1gx68vq6cpuKijr6SJ1aHOeCE+tqEbQs2pEllQmb+AefNg+PH2A2ElkBjjKKfMNoEw6GixZeRVewQFloDA2Ymf2Fp67zbvXlMJAIScHViS8h4yNUEtsSwODv1F7TkqbSfNtrMDJ4AilJ3kzXx0rSd8NWnSWZ0pVQOb91qJOhKnvzbm2IEIq+dk9Kw5FtIe07w=="
    shortcode = os.getenv("BUSINESS_SHORT_CODE") or os.getenv("MPESA_SHORTCODE") or "4050545"
    timeout_url = os.getenv("DARAJA_B2C_TIMEOUT_URL") or "https://www.findyourmatch.co.ke/mpesa/b2c/timeout"
    result_url = os.getenv("DARAJA_B2C_RESULT_URL") or "https://www.findyourmatch.co.ke/mpesa/b2c/result"

    try:
        clean_amount = int(round(float(amount)))
    except (ValueError, TypeError):
        return {"success": False, "error": f"Invalid payout amount: {amount}"}

    clean_receiver = ''.join(filter(str.isdigit, str(receiver_shortcode)))
    if not clean_receiver:
        return {"success": False, "error": "Receiver Till/Paybill number is required."}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {
        "Initiator": initiator,
        "SecurityCredential": credential,
        "CommandID": command_id,
        "SenderIdentifierType": "4",
        "RecieverIdentifierType": "4" if command_id == "BusinessPayBill" else "2",
        "Amount": clean_amount,
        "PartyA": shortcode,
        "PartyB": clean_receiver,
        "AccountReference": re.sub(r'[^a-zA-Z0-9]', '', str(account_reference))[:12] or "TicketCash",
        "Remarks": re.sub(r'[^a-zA-Z0-9 ]', '', str(remarks)).strip()[:20] or "Ticket Payout",
        "QueueTimeOutURL": timeout_url,
        "ResultURL": result_url
    }

    b2b_url = f"{BASE_URL}/mpesa/b2b/v1/paymentrequest"
    try:
        logger.info(f"📤 Sending B2B Payout: KES {clean_amount} to {clean_receiver} ({command_id})...")
        res = requests.post(b2b_url, json=payload, headers=headers, timeout=25)
        data = res.json()
        if res.status_code in [200, 201] and (data.get('ResponseCode') == '0' or 'ConversationID' in data):
            logger.info(f"✅ B2B Disbursed Successfully: ConversationID={data.get('ConversationID')}")
            return {
                "success": True,
                "ConversationID": data.get('ConversationID'),
                "OriginatorConversationID": data.get('OriginatorConversationID'),
                "ResponseDescription": data.get('ResponseDescription', 'Accepted'),
                "data": data
            }
        else:
            err_msg = data.get('errorMessage') or data.get('ResponseDescription') or str(data)
            logger.warning(f"⚠️ B2B response: {err_msg}")
            return {"success": False, "error": err_msg}
    except Exception as e:
        logger.error(f"❌ B2B request exception: {e}")
        return {"success": False, "error": str(e)}
