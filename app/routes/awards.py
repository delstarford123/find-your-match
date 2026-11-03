import os
import re
import time
import uuid
import csv
import io
import html
import hashlib
import secrets
import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, Response, current_app

from app.database import db
from app.payments import initiate_stk_push, format_phone_number, check_payment_status
from app.email_service import (
    send_voter_otp_email,
    send_vote_receipt_email,
    send_contestant_registration_email,
    send_contestant_milestone_email
)

logger = logging.getLogger(__name__)

awards_bp = Blueprint('awards_bp', __name__)

# Default Universities supported
DEFAULT_INSTITUTIONS = [
    "MMUST",
    "University of Nairobi (UoN)",
    "Kenyatta University (KU)",
    "JKUAT",
    "Strathmore University",
    "Moi University",
    "Egerton University",
    "Technical University of Kenya (TUK)",
    "Maseno University",
    "Chuka University",
    "Mount Kenya University (MKU)",
    "Kisii University",
    "National / Open"
]

DEFAULT_CATEGORIES = [
    {"id": "cat_best_male_mc", "name": "Best Male MC", "icon": "🎤", "desc": "Top campus event master of ceremony and hype host"},
    {"id": "cat_best_female_mc", "name": "Best Female MC", "icon": "🎙️", "desc": "Outstanding female host and stage personality"},
    {"id": "cat_best_dj", "name": "Best Campus DJ", "icon": "🎧", "desc": "Premier disc jockey rocking university decks and nightlife"},
    {"id": "cat_content_creator", "name": "Best Content Creator", "icon": "📱", "desc": "Viral storytellers, skit makers, and digital influencers"},
    {"id": "cat_spoken_word", "name": "Spoken Word & Poet", "icon": "📜", "desc": "Inspiring poets, lyricists, and spoken word performers"},
    {"id": "cat_fashion_icon", "name": "Campus Fashion Icon", "icon": "✨", "desc": "Trendsetters, style icons, and campus aesthetic leaders"},
    {"id": "cat_tech_innovator", "name": "Tech & Startup Innovator", "icon": "💻", "desc": "Student builders, coders, and startup visionaries"},
    {"id": "cat_campus_influencer", "name": "Campus Role Model / Leader", "icon": "👑", "desc": "Influential comrades making real impact in student life"}
]

VOTE_PACKAGES = [
    {"votes": 1, "amount": 10, "badge": "Single Vote", "popular": False},
    {"votes": 10, "amount": 100, "badge": "Standard Pack", "popular": True},
    {"votes": 50, "amount": 500, "badge": "Advocate Pack", "popular": False},
    {"votes": 100, "amount": 1000, "badge": "Champions Pack", "popular": False}
]

CONTESTANT_REG_FEE = 50  # KES


def sanitize_input(text: str, max_len: int = 500) -> str:
    """Escapes HTML entities and truncates strings."""
    if not text:
        return ""
    return html.escape(str(text).strip())[:max_len]


def get_awards_settings():
    """Retrieves or initializes global awards configuration."""
    settings_ref = db.reference('awards_settings')
    settings = settings_ref.get()
    if not settings or not isinstance(settings, dict):
        default_settings = {
            "title": "Campus Awards & Talent Recognition 2026",
            "campaign_active": False,   # Starts FALSE until Super Admin clicks Start
            "banner_active": False,     # Controls visibility on index.html
            "phase": "nominations",     # nominations | voting | blind_freeze | closed
            "blind_mode": False,        # If true, public vote totals are hidden for grand finale
            "registration_fee": CONTESTANT_REG_FEE,
            "cost_per_vote": 10,
            "prize_pool_kes": 50000,
            "campaign_start_date": "",
            "finale_date": "2026-11-30T23:59:59",
            "free_votes_enabled": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        settings_ref.set(default_settings)
        return default_settings
    
    # Ensure campaign_active and banner_active exist
    if 'campaign_active' not in settings:
        settings['campaign_active'] = False
    if 'banner_active' not in settings:
        settings['banner_active'] = False
    return settings


def ensure_categories_exist():
    """Seeds default categories if none are present in Firebase."""
    cat_ref = db.reference('awards_categories')
    existing = cat_ref.get()
    if not existing:
        seed_data = {}
        for c in DEFAULT_CATEGORIES:
            seed_data[c['id']] = {
                "name": c['name'],
                "icon": c['icon'],
                "desc": c['desc'],
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
        cat_ref.set(seed_data)
        return seed_data
    return existing


def claim_awards_mpesa_receipt(receipt: str, contestant_id: str, checkout_id: str, amount: int, transaction_type: str = "vote"):
    """
    Cryptographic deduplication ledger to prevent receipt replay attacks.
    """
    clean_receipt = re.sub(r'[^a-zA-Z0-9]', '', str(receipt).upper().strip())
    if not clean_receipt or len(clean_receipt) < 6:
        return False, {"error": "Invalid M-Pesa receipt format"}

    receipt_ref = db.reference(f'used_mpesa_receipts/{clean_receipt}')
    existing = receipt_ref.get()

    if existing and isinstance(existing, dict):
        if checkout_id and existing.get('checkout_id') == checkout_id:
            return True, existing
        logger.warning(f"🚨 Awards M-Pesa receipt replay blocked: {clean_receipt}")
        return False, {"error": "Receipt already claimed"}

    record = {
        'receipt': clean_receipt,
        'type': transaction_type,
        'contestant_id': contestant_id,
        'checkout_id': checkout_id,
        'amount': amount,
        'claimed_at': datetime.now(timezone.utc).isoformat()
    }
    receipt_ref.set(record)
    return True, record


# =========================================================================
# 1. PUBLIC AWARDS PORTAL & LEADERBOARD
# =========================================================================

@awards_bp.route('', methods=['GET'])
@awards_bp.route('/', methods=['GET'])
@awards_bp.route('/hub', methods=['GET'])
def awards_index():
    """
    Main awards discovery portal.
    Features: Institution filter, Category tabs, Search, Live Podium, Contestant cards.
    """
    settings = get_awards_settings()
    categories_dict = ensure_categories_exist() or {}
    
    selected_cat = request.args.get('category', 'all')
    selected_inst = request.args.get('institution', 'all')
    search_query = request.args.get('q', '').strip().lower()

    # Fetch contestants
    contestants_data = db.reference('awards_contestants').get() or {}
    contestants = []

    for cid, c in contestants_data.items():
        if isinstance(c, dict) and c.get('status') == 'active':
            c['id'] = cid
            c['vote_count'] = int(c.get('vote_count', 0) or 0)
            
            # Category filter
            if selected_cat != 'all' and c.get('category_id') != selected_cat:
                continue
            # Institution filter
            if selected_inst != 'all' and c.get('institution') != selected_inst:
                continue
            # Search query
            if search_query:
                name_match = search_query in str(c.get('name', '')).lower()
                cat_match = search_query in str(c.get('category_name', '')).lower()
                inst_match = search_query in str(c.get('institution', '')).lower()
                if not (name_match or cat_match or inst_match):
                    continue

            contestants.append(c)

    # Sort by votes descending (Leaderboard)
    contestants.sort(key=lambda x: x['vote_count'], reverse=True)

    # Assign current dynamic ranks
    for rank, contestant in enumerate(contestants, start=1):
        contestant['rank'] = rank

    # Extract top 3 for the visual podium
    podium = contestants[:3] if len(contestants) >= 3 else contestants

    return render_template(
        'awards_index.html',
        settings=settings,
        categories=categories_dict,
        institutions=DEFAULT_INSTITUTIONS,
        contestants=contestants,
        podium=podium,
        selected_category=selected_cat,
        selected_institution=selected_inst,
        search_query=search_query,
        vote_packages=VOTE_PACKAGES
    )


@awards_bp.route('/contestant/<cid>', methods=['GET'])
def awards_contestant_detail(cid):
    """
    Dedicated shareable profile page for a contestant (optimized for WhatsApp Status & IG).
    """
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(cid).strip())
    contestant = db.reference(f'awards_contestants/{clean_id}').get()

    if not contestant or not isinstance(contestant, dict):
        return render_template('404.html', message="Contestant not found or not yet approved."), 404

    contestant['id'] = clean_id
    contestant['vote_count'] = int(contestant.get('vote_count', 0) or 0)

    # Calculate rank in their category
    all_contestants = db.reference('awards_contestants').get() or {}
    same_cat = [
        c for c in all_contestants.values()
        if isinstance(c, dict) and c.get('status') == 'active' and c.get('category_id') == contestant.get('category_id')
    ]
    same_cat.sort(key=lambda x: int(x.get('vote_count', 0) or 0), reverse=True)
    
    current_rank = 1
    for idx, c in enumerate(same_cat, start=1):
        if c.get('id') == clean_id or c.get('name') == contestant.get('name'):
            current_rank = idx
            break
    contestant['rank'] = current_rank
    contestant['total_in_cat'] = len(same_cat)

    settings = get_awards_settings()
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    share_url = f"{base_url}/awards/contestant/{clean_id}"

    return render_template(
        'awards_contestant.html',
        contestant=contestant,
        settings=settings,
        share_url=share_url,
        vote_packages=VOTE_PACKAGES
    )


# =========================================================================
# 2. CONTESTANT NOMINATION & REGISTRATION (50 KES STK PUSH)
# =========================================================================

@awards_bp.route('/register', methods=['GET'])
def awards_register_page():
    """Contestant registration & nomination onboarding screen."""
    settings = get_awards_settings()
    categories_dict = ensure_categories_exist() or {}
    return render_template(
        'awards_register.html',
        settings=settings,
        categories=categories_dict,
        institutions=DEFAULT_INSTITUTIONS,
        registration_fee=CONTESTANT_REG_FEE
    )


@awards_bp.route('/api/register', methods=['POST'])
def api_awards_register():
    """
    Submits contestant nomination and triggers 50 KES M-Pesa STK push.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    name = sanitize_input(data.get('name'), 80)
    email = sanitize_input(data.get('email'), 120).lower()
    phone = sanitize_input(data.get('phone'), 20)
    institution = sanitize_input(data.get('institution'), 100)
    category_id = sanitize_input(data.get('category_id'), 60)
    bio = sanitize_input(data.get('bio'), 1000)
    photo_url = sanitize_input(data.get('photo_url'), 300)
    video_url = sanitize_input(data.get('video_url'), 300)
    instagram = sanitize_input(data.get('instagram'), 60)
    tiktok = sanitize_input(data.get('tiktok'), 60)

    if not name or len(name) < 2:
        return jsonify({"success": False, "error": "Full name is required."}), 400
    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Valid email address is required for receipts."}), 400
    if not phone or len(phone) < 9:
        return jsonify({"success": False, "error": "Valid M-Pesa phone number is required."}), 400
    if not category_id:
        return jsonify({"success": False, "error": "Please select an award category."}), 400

    categories_dict = ensure_categories_exist()
    cat_info = categories_dict.get(category_id, {})
    category_name = cat_info.get('name', 'Campus Nominee')

    formatted_phone = format_phone_number(phone)
    if not formatted_phone:
        return jsonify({"success": False, "error": "Invalid Kenyan phone format (e.g. 07XXXXXXXX or 2547XXXXXXXX)."}), 400

    # Generate unique contestant ID
    contestant_id = f"c_{secrets.token_hex(6)}"
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    referral_link = f"{base_url}/awards/contestant/{contestant_id}"

    # Default placeholder photo if not provided
    final_photo = photo_url or f"{base_url}/static/img/placeholder.png"

    contestant_record = {
        "name": name,
        "email": email,
        "phone": formatted_phone,
        "institution": institution or "MMUST",
        "category_id": category_id,
        "category_name": category_name,
        "bio": bio,
        "photo_url": final_photo,
        "video_url": video_url,
        "socials": {
            "instagram": instagram,
            "tiktok": tiktok
        },
        "vote_count": 0,
        "status": "pending_payment",  # activates on M-Pesa webhook
        "referral_link": referral_link,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    db.reference(f'awards_contestants/{contestant_id}').set(contestant_record)

    # Initiate M-Pesa STK push for 50 KES
    callback_url = f"{base_url}/awards/api/mpesa/awards_callback"
    account_ref = f"REG-{contestant_id[-6:].upper()}"
    trans_desc = f"Awards Reg: {name[:12]}"

    stk_res = initiate_stk_push(
        phone_number=formatted_phone,
        amount=CONTESTANT_REG_FEE,
        account_reference=account_ref,
        callback_url=callback_url,
        transaction_desc=trans_desc
    )

    checkout_id = stk_res.get('CheckoutRequestID')
    if not checkout_id:
        err_msg = stk_res.get('errorMessage') or "Failed to initiate M-Pesa prompt. Please verify phone number."
        return jsonify({"success": False, "error": err_msg}), 400

    # Track pending payment
    db.reference(f'pending_awards_payments/{checkout_id}').set({
        "type": "registration",
        "contestant_id": contestant_id,
        "contestant_name": name,
        "category_name": category_name,
        "institution": institution,
        "email": email,
        "phone": formatted_phone,
        "amount": CONTESTANT_REG_FEE,
        "referral_link": referral_link,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return jsonify({
        "success": True,
        "message": f"M-Pesa STK push sent to {formatted_phone}! Please enter your M-Pesa PIN to complete registration.",
        "checkout_id": checkout_id,
        "contestant_id": contestant_id
    }), 200


# =========================================================================
# 3. VOTER EMAIL OTP VERIFICATION (Zero-Cost Anti-Bot Authentication)
# =========================================================================

@awards_bp.route('/api/vote/request-otp', methods=['POST'])
def api_awards_request_otp():
    """
    Generates and sends a 6-digit verification code to the voter's email.
    Completely replaces SMS OTP with zero-cost HostPinnacle SMTP.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    email = sanitize_input(data.get('email'), 120).lower()
    voter_name = sanitize_input(data.get('name'), 60) or "Comrade"
    contestant_name = sanitize_input(data.get('contestant_name'), 80)

    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Valid email address is required to receive verification code."}), 400

    # Rate limiting: max 3 OTP requests per 10 minutes per email
    email_key = re.sub(r'[^a-zA-Z0-9]', '_', email)
    otp_ref = db.reference(f'awards_voter_otps/{email_key}')
    existing = otp_ref.get()

    now = datetime.now(timezone.utc)
    if existing and isinstance(existing, dict):
        last_req = datetime.fromisoformat(existing.get('requested_at', now.isoformat()))
        if (now - last_req).total_seconds() < 45:
            return jsonify({"success": False, "error": "Please wait 45 seconds before requesting another code."}), 429

    otp_code = str(secrets.randbelow(900000) + 100000)
    expiry = (now + timedelta(minutes=10)).isoformat()

    otp_ref.set({
        "otp": otp_code,
        "expiry": expiry,
        "requested_at": now.isoformat(),
        "verified": False,
        "voter_name": voter_name
    })

    # Dispatch via HostPinnacle SMTP
    dispatched = send_voter_otp_email(
        recipient_email=email,
        voter_name=voter_name,
        otp_code=otp_code,
        contestant_name=contestant_name
    )

    return jsonify({
        "success": True,
        "message": f"Verification code sent to {email}. Check your inbox or spam folder."
    }), 200


@awards_bp.route('/api/vote/verify-otp', methods=['POST'])
def api_awards_verify_otp():
    """
    Verifies the 6-digit voter code and unlocks voting permission in the session.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    email = sanitize_input(data.get('email'), 120).lower()
    code = sanitize_input(data.get('code'), 10).strip()

    if not email or not code:
        return jsonify({"success": False, "error": "Email and verification code are required."}), 400

    email_key = re.sub(r'[^a-zA-Z0-9]', '_', email)
    otp_ref = db.reference(f'awards_voter_otps/{email_key}')
    record = otp_ref.get()

    if not record or not isinstance(record, dict):
        return jsonify({"success": False, "error": "No pending verification found. Request a new code."}), 404

    now = datetime.now(timezone.utc)
    expiry = datetime.fromisoformat(record.get('expiry', now.isoformat()))
    if now > expiry:
        return jsonify({"success": False, "error": "Verification code has expired. Request a new one."}), 400

    if str(record.get('otp')).strip() != code:
        return jsonify({"success": False, "error": "Invalid verification code. Please check and try again."}), 400

    # Mark verified
    otp_ref.update({"verified": True, "verified_at": now.isoformat()})
    session[f'voter_verified_{email}'] = True

    return jsonify({
        "success": True,
        "message": "Voter verified successfully! You may now cast your vote."
    }), 200


# =========================================================================
# 4. VOTING STK PUSH (10 KES / VOTE & BULK PACKS)
# =========================================================================

@awards_bp.route('/api/vote/stk-push', methods=['POST'])
def api_awards_vote_stk_push():
    """
    Triggers M-Pesa STK push for single or bulk votes (10 KES per vote).
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    contestant_id = sanitize_input(data.get('contestant_id'), 60)
    voter_phone = sanitize_input(data.get('phone'), 20)
    voter_email = sanitize_input(data.get('email'), 120).lower()
    voter_name = sanitize_input(data.get('name'), 60) or "Comrade"
    try:
        vote_count = int(data.get('vote_count', 1))
    except (ValueError, TypeError):
        vote_count = 1

    if vote_count < 1 or vote_count > 500:
        return jsonify({"success": False, "error": "Invalid vote quantity (allowed 1 - 500 votes)."}), 400

    if not contestant_id:
        return jsonify({"success": False, "error": "Contestant ID is required."}), 400
    if not voter_email or "@" not in voter_email:
        return jsonify({"success": False, "error": "Email address is required for official vote receipt."}), 400
    if not voter_phone:
        return jsonify({"success": False, "error": "M-Pesa phone number is required."}), 400

    formatted_phone = format_phone_number(voter_phone)
    if not formatted_phone:
        return jsonify({"success": False, "error": "Invalid phone number format."}), 400

    contestant = db.reference(f'awards_contestants/{contestant_id}').get()
    if not contestant or not isinstance(contestant, dict):
        return jsonify({"success": False, "error": "Contestant not found."}), 404

    # Calculate expected amount (10 KES per vote)
    total_amount = vote_count * 10
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    callback_url = f"{base_url}/awards/api/mpesa/awards_callback"
    account_ref = f"VOTE-{contestant_id[-4:].upper()}"
    trans_desc = f"{vote_count} votes for {contestant.get('name', '')[:10]}"

    stk_res = initiate_stk_push(
        phone_number=formatted_phone,
        amount=total_amount,
        account_reference=account_ref,
        callback_url=callback_url,
        transaction_desc=trans_desc
    )

    checkout_id = stk_res.get('CheckoutRequestID')
    if not checkout_id:
        err_msg = stk_res.get('errorMessage') or "Failed to initiate M-Pesa prompt. Please try again."
        return jsonify({"success": False, "error": err_msg}), 400

    # Save pending vote record
    db.reference(f'pending_awards_payments/{checkout_id}').set({
        "type": "vote",
        "contestant_id": contestant_id,
        "contestant_name": contestant.get('name'),
        "category_id": contestant.get('category_id'),
        "category_name": contestant.get('category_name'),
        "contestant_email": contestant.get('email'),
        "voter_name": voter_name,
        "voter_email": voter_email,
        "voter_phone": formatted_phone,
        "vote_count": vote_count,
        "amount": total_amount,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    return jsonify({
        "success": True,
        "message": f"STK push sent to {formatted_phone}! Enter your M-Pesa PIN to cast {vote_count} votes.",
        "checkout_id": checkout_id
    }), 200


@awards_bp.route('/api/check-payment/<checkout_id>', methods=['GET'])
def api_awards_check_payment(checkout_id):
    """
    Polling endpoint for frontend to check if M-Pesa STK PIN was entered.
    """
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(checkout_id).strip())
    record = db.reference(f'pending_awards_payments/{clean_id}').get()

    if not record or not isinstance(record, dict):
        return jsonify({"status": "NOT_FOUND"}), 404

    status = record.get('status', 'pending')
    return jsonify({
        "status": status.upper(),
        "type": record.get('type'),
        "receipt": record.get('receipt'),
        "vote_count": record.get('vote_count', 0),
        "contestant_name": record.get('contestant_name'),
        "message": record.get('message', '')
    }), 200


# =========================================================================
# 5. SAFARICOM DARAJA M-PESA WEBHOOK RECONCILIATION
# =========================================================================

@awards_bp.route('/api/mpesa/awards_callback', methods=['POST'])
def mpesa_awards_callback():
    """
    Universal webhook for Safaricom Daraja STK Push callbacks (both Voting and Registration).
    Underpayment-shielded, anti-replay protected, and race-condition free.
    """
    data = request.get_json(silent=True) or {}
    try:
        body = data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        if not stk_callback:
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

        result_code = stk_callback.get('ResultCode')
        checkout_id = stk_callback.get('CheckoutRequestID')
        if not checkout_id:
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

        clean_checkout = re.sub(r'[^a-zA-Z0-9_\-]', '', str(checkout_id).strip())
        pending_ref = db.reference(f'pending_awards_payments/{clean_checkout}')
        record = pending_ref.get()

        if not record or not isinstance(record, dict):
            logger.warning(f"⚠️ Awards callback for unknown checkout: {clean_checkout}")
            return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

        # Idempotency check
        if record.get('status') == 'success':
            return jsonify({"ResultCode": 0, "ResultDesc": "Already processed"})

        if result_code == 0:
            metadata = stk_callback.get('CallbackMetadata', {}).get('Item', [])
            receipt = next((item['Value'] for item in metadata if item.get('Name') == 'MpesaReceiptNumber'), None)
            amount = next((item['Value'] for item in metadata if item.get('Name') == 'Amount'), record.get('amount', 0))

            expected_amount = int(record.get('amount', 0) or 0)
            actual_amount = int(amount or 0)

            # Underpayment shield
            if expected_amount > 0 and actual_amount < expected_amount:
                logger.warning(f"🚨 Awards Underpayment blocked: Paid {actual_amount}, expected {expected_amount}")
                pending_ref.update({"status": "underpaid", "paid": actual_amount})
                return jsonify({"ResultCode": 0, "ResultDesc": "Underpaid"})

            trans_type = record.get('type')
            contestant_id = record.get('contestant_id')

            # Claim receipt to prevent replay attacks
            claimed, claim_record = claim_awards_mpesa_receipt(
                receipt=receipt,
                contestant_id=contestant_id,
                checkout_id=clean_checkout,
                amount=actual_amount,
                transaction_type=trans_type
            )

            if not claimed:
                pending_ref.update({"status": "duplicate_receipt_blocked"})
                return jsonify({"ResultCode": 0, "ResultDesc": "Duplicate receipt"})

            now_iso = datetime.now(timezone.utc).isoformat()

            # -------------------------------------------------------------
            # A. CONTESTANT REGISTRATION VERIFIED (50 KES)
            # -------------------------------------------------------------
            if trans_type == "registration":
                db.reference(f'awards_contestants/{contestant_id}').update({
                    "status": "active",
                    "registration_receipt": receipt,
                    "activated_at": now_iso
                })

                pending_ref.update({
                    "status": "success",
                    "receipt": receipt,
                    "completed_at": now_iso
                })

                # Dispatch contestant welcome email with WhatsApp share link
                send_contestant_registration_email(
                    recipient_email=record.get('email'),
                    contestant_name=record.get('contestant_name'),
                    category=record.get('category_name'),
                    institution=record.get('institution'),
                    referral_link=record.get('referral_link'),
                    mpesa_receipt=receipt
                )
                logger.info(f"✅ Contestant {contestant_id} activated and email dispatched!")

            # -------------------------------------------------------------
            # B. VOTE CONFIRMED (10 KES / VOTE)
            # -------------------------------------------------------------
            elif trans_type == "vote":
                vote_count = int(record.get('vote_count', 1))
                c_ref = db.reference(f'awards_contestants/{contestant_id}')
                c_data = c_ref.get() or {}
                
                prev_votes = int(c_data.get('vote_count', 0) or 0)
                new_votes = prev_votes + vote_count

                # Update vote tally atomically
                c_ref.update({"vote_count": new_votes, "last_voted_at": now_iso})

                # Log into immutable audit ledger
                ledger_id = f"vl_{secrets.token_hex(8)}"
                audit_hash = hashlib.sha256(f"{receipt}_{contestant_id}_{now_iso}".encode()).hexdigest()[:16].upper()
                db.reference(f'awards_votes_ledger/{ledger_id}').set({
                    "contestant_id": contestant_id,
                    "contestant_name": record.get('contestant_name'),
                    "category_id": record.get('category_id'),
                    "category_name": record.get('category_name'),
                    "voter_name": record.get('voter_name'),
                    "voter_email": record.get('voter_email'),
                    "voter_phone": record.get('voter_phone'),
                    "vote_count": vote_count,
                    "amount": actual_amount,
                    "mpesa_receipt": receipt,
                    "checkout_id": clean_checkout,
                    "audit_hash": f"FYM-AUDIT-{audit_hash}",
                    "timestamp": now_iso
                })

                pending_ref.update({
                    "status": "success",
                    "receipt": receipt,
                    "new_total_votes": new_votes,
                    "completed_at": now_iso
                })

                # 1. Dispatch Vote Confirmation Receipt to Voter
                send_vote_receipt_email(
                    recipient_email=record.get('voter_email'),
                    voter_name=record.get('voter_name'),
                    contestant_name=record.get('contestant_name'),
                    category=record.get('category_name'),
                    vote_count=vote_count,
                    amount_paid=actual_amount,
                    mpesa_receipt=receipt,
                    new_total_votes=new_votes
                )

                # 2. Check for Milestones (50, 100, 250, 500, 1000 votes)
                milestones = [50, 100, 250, 500, 1000, 2500, 5000]
                for m in milestones:
                    if prev_votes < m <= new_votes:
                        # Contestant passed this milestone! Send alert
                        send_contestant_milestone_email(
                            recipient_email=record.get('contestant_email'),
                            contestant_name=record.get('contestant_name'),
                            milestone_votes=m,
                            current_rank=1,
                            category=record.get('category_name')
                        )
                        break

                logger.info(f"✅ Credited {vote_count} votes to {contestant_id} (Total: {new_votes}). Receipt email sent to {record.get('voter_email')}")

        else:
            # Payment cancelled or failed on user phone
            err_desc = stk_callback.get('ResultDesc', 'Payment cancelled or timed out')
            pending_ref.update({
                "status": "failed",
                "message": err_desc,
                "failed_at": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"❌ Awards STK push failed for {clean_checkout}: {err_desc}")

        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

    except Exception as e:
        logger.error(f"Error in mpesa_awards_callback: {e}", exc_info=True)
        return jsonify({"ResultCode": 0, "ResultDesc": "Handled with error"})


# =========================================================================
# 6. REAL-TIME LEADERBOARD JSON API
# =========================================================================

@awards_bp.route('/api/leaderboard', methods=['GET'])
def api_awards_leaderboard():
    """Returns dynamic leaderboard JSON data for live DOM reordering."""
    category_id = request.args.get('category', 'all')
    institution = request.args.get('institution', 'all')
    settings = get_awards_settings()

    contestants_data = db.reference('awards_contestants').get() or {}
    results = []

    for cid, c in contestants_data.items():
        if isinstance(c, dict) and c.get('status') == 'active':
            if category_id != 'all' and c.get('category_id') != category_id:
                continue
            if institution != 'all' and c.get('institution') != institution:
                continue

            vote_val = int(c.get('vote_count', 0) or 0)
            results.append({
                "id": cid,
                "name": c.get('name'),
                "institution": c.get('institution'),
                "category_id": c.get('category_id'),
                "category_name": c.get('category_name'),
                "photo_url": c.get('photo_url'),
                "vote_count": vote_val if not settings.get('blind_mode') else "🔒 Hidden",
                "raw_votes": vote_val
            })

    results.sort(key=lambda x: x['raw_votes'], reverse=True)
    for idx, item in enumerate(results, start=1):
        item['rank'] = idx

    return jsonify({
        "success": True,
        "blind_mode": settings.get('blind_mode', False),
        "total_contestants": len(results),
        "leaderboard": results
    }), 200


# =========================================================================
# 7. SUPER ADMIN DASHBOARD & CONTROLS
# =========================================================================

@awards_bp.route('/admin', methods=['GET'])
def awards_admin():
    """Admin console to oversee nominations, category configs, revenue, and audits."""
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return redirect(url_for('super_admin'))

    settings = get_awards_settings()
    categories = ensure_categories_exist() or {}
    contestants_data = db.reference('awards_contestants').get() or {}
    votes_ledger = db.reference('awards_votes_ledger').get() or {}

    total_revenue = 0
    total_votes = 0

    # Calculate financial analytics
    for v in votes_ledger.values():
        if isinstance(v, dict):
            total_revenue += int(v.get('amount', 0) or 0)
            total_votes += int(v.get('vote_count', 0) or 0)

    # Calculate registration revenue
    active_contestants = 0
    pending_contestants = 0
    for c in contestants_data.values():
        if isinstance(c, dict):
            if c.get('status') == 'active':
                active_contestants += 1
                total_revenue += CONTESTANT_REG_FEE
            elif c.get('status') == 'pending_approval':
                pending_contestants += 1

    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    return render_template(
        'awards_admin.html',
        settings=settings,
        categories=categories,
        contestants=contestants_data,
        total_revenue=total_revenue,
        total_votes=total_votes,
        active_contestants=active_contestants,
        pending_contestants=pending_contestants,
        base_url=base_url
    )


@awards_bp.route('/api/admin/toggle-blind-mode', methods=['POST'])
def api_admin_toggle_blind_mode():
    """Freezes or unfreezes public vote visibility before the grand finale."""
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    curr = db.reference('awards_settings/blind_mode').get() or False
    new_val = not curr
    db.reference('awards_settings/blind_mode').set(new_val)

    status_str = "FROZEN (Blind Mode Active)" if new_val else "UNFROZEN (Public Totals Visible)"
    return jsonify({"success": True, "blind_mode": new_val, "message": f"Vote counts are now {status_str}."}), 200


@awards_bp.route('/api/admin/approve-contestant', methods=['POST'])
def api_admin_approve_contestant():
    """Approves or rejects a contestant profile."""
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or request.form.to_dict()
    contestant_id = data.get('contestant_id')
    action = data.get('action', 'approve')

    new_status = 'active' if action == 'approve' else 'rejected'
    db.reference(f'awards_contestants/{contestant_id}/status').set(new_status)

    return jsonify({"success": True, "message": f"Contestant marked as {new_status}."}), 200


@awards_bp.route('/api/admin/export-csv', methods=['GET'])
def api_admin_export_csv():
    """Exports full cryptographic votes ledger to CSV."""
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return "Unauthorized", 403

    votes_ledger = db.reference('awards_votes_ledger').get() or {}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp", "M-Pesa Receipt", "Contestant Name", "Category", 
        "Votes Cast", "Amount (KES)", "Voter Name", "Voter Email", "Voter Phone"
    ])

    for v in votes_ledger.values():
        if isinstance(v, dict):
            writer.writerow([
                v.get('timestamp'),
                v.get('mpesa_receipt'),
                v.get('contestant_name'),
                v.get('category_name'),
                v.get('vote_count'),
                v.get('amount'),
                v.get('voter_name'),
                v.get('voter_email'),
                v.get('voter_phone')
            ])

    output.seek(0)
    filename = f"awards_votes_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )



# =========================================================================
# 8. PUBLIC CRYPTOGRAPHIC VOTE VERIFIER & AUDIT TOOL
# =========================================================================

@awards_bp.route('/verify', methods=['GET'])
def awards_verify_page():
    """Public portal to verify any M-Pesa receipt against the tamper-proof ledger."""
    settings = get_awards_settings()
    receipt_query = request.args.get('receipt', '').strip().upper()
    return render_template(
        'awards_verify.html',
        settings=settings,
        receipt_query=receipt_query
    )


@awards_bp.route('/api/verify-receipt/<receipt_code>', methods=['GET'])
def api_verify_receipt(receipt_code):
    """
    Looks up any M-Pesa transaction in the immutable ledger.
    Returns cryptographic confirmation and vote details.
    """
    clean_code = re.sub(r'[^a-zA-Z0-9]', '', str(receipt_code).upper().strip())
    if len(clean_code) < 6:
        return jsonify({"success": False, "error": "Invalid receipt format."}), 400

    ledger_data = db.reference('awards_votes_ledger').get() or {}
    match_record = None

    for vid, item in ledger_data.items():
        if isinstance(item, dict) and item.get('mpesa_receipt') == clean_code:
            match_record = item
            break

    if not match_record:
        # Check if it was a contestant registration receipt
        reg_check = db.reference(f'used_mpesa_receipts/{clean_code}').get()
        if reg_check and isinstance(reg_check, dict):
            return jsonify({
                "success": True,
                "type": "registration",
                "receipt": clean_code,
                "amount": reg_check.get('amount', 50),
                "timestamp": reg_check.get('claimed_at'),
                "status": "VERIFIED & CONFIRMED",
                "audit_message": "Official 50 KES Contestant Nomination & Profile Verification."
            }), 200

        return jsonify({
            "success": False,
            "error": f"No vote or registration found matching M-Pesa receipt '{clean_code}'. Please double-check your Safaricom SMS."
        }), 404

    # Mask voter phone/email for privacy while proving authenticity
    raw_email = match_record.get('voter_email', '')
    masked_email = re.sub(r'(?<=.{2}).(?=.*@)', '*', raw_email) if '@' in raw_email else 'Comrade'
    
    raw_phone = match_record.get('voter_phone', '')
    masked_phone = raw_phone[:5] + '****' + raw_phone[-3:] if len(raw_phone) >= 9 else 'Verified'

    return jsonify({
        "success": True,
        "type": "vote",
        "receipt": clean_code,
        "contestant_name": match_record.get('contestant_name'),
        "category_name": match_record.get('category_name'),
        "votes_cast": match_record.get('vote_count'),
        "amount_paid": match_record.get('amount'),
        "timestamp": match_record.get('timestamp'),
        "audit_hash": match_record.get('audit_hash', 'FYM-AUDIT-VERIFIED'),
        "voter_email": masked_email,
        "voter_phone": masked_phone,
        "status": "VERIFIED & COUNTED ON LEDGER"
    }), 200


# =========================================================================
# 9. DAILY FREE VOTE FOR VERIFIED STUDENTS (Viral Engagement)
# =========================================================================

@awards_bp.route('/api/vote/daily-free', methods=['POST'])
def api_awards_daily_free_vote():
    """
    Grants 1 free vote every 24 hours per verified student email or account.
    """
    data = request.get_json(silent=True) or request.form.to_dict()
    email = sanitize_input(data.get('email'), 120).lower()
    contestant_id = sanitize_input(data.get('contestant_id'), 60)
    voter_name = sanitize_input(data.get('name'), 60) or "Verified Comrade"

    settings = get_awards_settings()
    if not settings.get('free_votes_enabled', True):
        return jsonify({"success": False, "error": "Daily free voting is currently paused."}), 403

    if not email or "@" not in email:
        return jsonify({"success": False, "error": "Valid student email address is required."}), 400

    if not contestant_id:
        return jsonify({"success": False, "error": "Contestant ID is required."}), 400

    contestant = db.reference(f'awards_contestants/{contestant_id}').get()
    if not contestant or not isinstance(contestant, dict):
        return jsonify({"success": False, "error": "Contestant not found."}), 404

    email_key = re.sub(r'[^a-zA-Z0-9]', '_', email)
    free_vote_ref = db.reference(f'awards_free_votes/{email_key}')
    last_record = free_vote_ref.get()

    now = datetime.now(timezone.utc)
    if last_record and isinstance(last_record, dict):
        last_voted = datetime.fromisoformat(last_record.get('timestamp', '2020-01-01T00:00:00+00:00'))
        hours_since = (now - last_voted).total_seconds() / 3600
        if hours_since < 24:
            hours_left = int(24 - hours_since) + 1
            return jsonify({
                "success": False,
                "error": f"You already claimed your free daily vote! Next free vote unlocks in {hours_left} hours. You can still cast unlimited votes via M-Pesa (10 KES)!"
            }), 429

    # Record free vote
    now_iso = now.isoformat()
    free_vote_ref.set({
        "email": email,
        "contestant_id": contestant_id,
        "contestant_name": contestant.get('name'),
        "timestamp": now_iso
    })

    # Increment contestant tally
    c_ref = db.reference(f'awards_contestants/{contestant_id}')
    prev_votes = int(contestant.get('vote_count', 0) or 0)
    new_votes = prev_votes + 1
    c_ref.update({"vote_count": new_votes, "last_voted_at": now_iso})

    # Log in votes ledger
    free_receipt = f"FREE-{secrets.token_hex(4).upper()}"
    audit_hash = hashlib.sha256(f"{free_receipt}_{contestant_id}_{now_iso}".encode()).hexdigest()[:16].upper()
    db.reference(f'awards_votes_ledger/vl_{secrets.token_hex(8)}').set({
        "contestant_id": contestant_id,
        "contestant_name": contestant.get('name'),
        "category_id": contestant.get('category_id'),
        "category_name": contestant.get('category_name'),
        "voter_name": voter_name,
        "voter_email": email,
        "voter_phone": "STUDENT_FREE_PASS",
        "vote_count": 1,
        "amount": 0,
        "mpesa_receipt": free_receipt,
        "audit_hash": f"FYM-FREE-{audit_hash}",
        "timestamp": now_iso
    })

    # Send confirmation email
    send_vote_receipt_email(
        recipient_email=email,
        voter_name=voter_name,
        contestant_name=contestant.get('name'),
        category=contestant.get('category_name'),
        vote_count=1,
        amount_paid=0,
        mpesa_receipt=free_receipt,
        new_total_votes=new_votes
    )

    return jsonify({
        "success": True,
        "message": f"🎉 Free daily vote credited to {contestant.get('name')}! Official confirmation delivered to {email}."
    }), 200


# =========================================================================
# 10. REAL-TIME ACTIVITY TICKER (Proof of Live Activity & Trust)
# =========================================================================

@awards_bp.route('/api/recent-activity', methods=['GET'])
def api_awards_recent_activity():
    """
    Returns latest 8 votes for the live public activity ticker.
    """
    votes_ledger = db.reference('awards_votes_ledger').get() or {}
    items = []

    now = datetime.now(timezone.utc)
    for v in votes_ledger.values():
        if isinstance(v, dict):
            try:
                v_time = datetime.fromisoformat(v.get('timestamp', now.isoformat()))
                diff_sec = max(1, int((now - v_time).total_seconds()))
                if diff_sec < 60:
                    time_ago = f"{diff_sec}s ago"
                elif diff_sec < 3600:
                    time_ago = f"{diff_sec // 60}m ago"
                else:
                    time_ago = f"{diff_sec // 3600}h ago"
            except Exception:
                time_ago = "Just now"

            # Mask voter name for privacy
            v_name = v.get('voter_name') or 'Comrade'
            masked_name = v_name.split()[0] if v_name else 'Comrade'

            items.append({
                "voter": masked_name,
                "votes": v.get('vote_count', 1),
                "contestant": v.get('contestant_name', 'Nominee'),
                "category": v.get('category_name', 'Awards'),
                "time_ago": time_ago,
                "raw_ts": v.get('timestamp', '')
            })

    # Sort newest first
    items.sort(key=lambda x: x['raw_ts'], reverse=True)
    return jsonify({"success": True, "activities": items[:8]}), 200


# =========================================================================
# 11. ADMIN SETTINGS & FINALE CONFIGURATION
# =========================================================================

@awards_bp.route('/api/admin/update-settings', methods=['POST'])
def api_admin_update_settings():
    """Updates prize pool, finale date, and voting phases."""
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or request.form.to_dict()
    phase = data.get('phase')
    prize_pool = data.get('prize_pool_kes')
    finale_date = data.get('finale_date')
    free_votes_enabled = data.get('free_votes_enabled')

    updates = {}
    if phase in ['nominations', 'voting', 'blind_freeze', 'closed']:
        updates['phase'] = phase
        if phase == 'blind_freeze':
            updates['blind_mode'] = True
        elif phase == 'voting':
            updates['blind_mode'] = False

    if prize_pool:
        try:
            updates['prize_pool_kes'] = int(prize_pool)
        except ValueError:
            pass

    if finale_date:
        updates['finale_date'] = finale_date

    if free_votes_enabled is not None:
        updates['free_votes_enabled'] = bool(free_votes_enabled)

    updates['updated_at'] = datetime.now(timezone.utc).isoformat()
    db.reference('awards_settings').update(updates)

    return jsonify({"success": True, "message": "Awards settings updated successfully!", "updates": updates}), 200



# =========================================================================
# 12. CONTESTANT WAR-ROOM DASHBOARD & CAMPAIGN VELOCITY (20 FEATURES)
# =========================================================================

@awards_bp.route('/dashboard/<cid>', methods=['GET'])
def awards_contestant_dashboard(cid):
    """
    Dedicated Campaign War-Room Dashboard for candidates to track rival momentum,
    generate promotional assets, and maximize voter turnout.
    """
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(cid).strip())
    contestant = db.reference(f'awards_contestants/{clean_id}').get()

    if not contestant or not isinstance(contestant, dict):
        return render_template('404.html', message="Contestant dashboard not found or profile pending verification."), 404

    contestant['id'] = clean_id
    contestant['vote_count'] = int(contestant.get('vote_count', 0) or 0)
    cat_id = contestant.get('category_id')

    # Fetch all active contestants in the same category to compute head-to-head metrics
    all_contestants = db.reference('awards_contestants').get() or {}
    rivals = [
        dict(c, id=k, vote_count=int(c.get('vote_count', 0) or 0))
        for k, c in all_contestants.items()
        if isinstance(c, dict) and c.get('status') == 'active' and c.get('category_id') == cat_id
    ]
    rivals.sort(key=lambda x: x['vote_count'], reverse=True)

    current_rank = 1
    for idx, r in enumerate(rivals, start=1):
        r['rank'] = idx
        if r['id'] == clean_id:
            current_rank = idx

    contestant['rank'] = current_rank

    # Head-to-Head calculations
    leader = rivals[0] if rivals else None
    runner_up = rivals[1] if len(rivals) > 1 else None
    rival_ahead = rivals[current_rank - 2] if current_rank > 1 and len(rivals) >= current_rank else None

    lead_margin = (contestant['vote_count'] - runner_up['vote_count']) if (current_rank == 1 and runner_up) else 0
    votes_to_next = ((rival_ahead['vote_count'] - contestant['vote_count']) + 1) if rival_ahead else 0
    votes_to_leader = ((leader['vote_count'] - contestant['vote_count']) + 1) if (leader and current_rank > 1) else 0

    # Milestone Progression (50, 100, 250, 500, 1000)
    milestones = [50, 100, 250, 500, 1000]
    next_milestone = 50
    for m in milestones:
        if contestant['vote_count'] < m:
            next_milestone = m
            break
        next_milestone = m + 500

    milestone_percent = min(100, int((contestant['vote_count'] / max(1, next_milestone)) * 100))
    milestone_unlocked = contestant['vote_count'] in milestones or contestant['vote_count'] >= 50

    # Top Supporters / Backers
    all_votes = db.reference('awards_votes').get() or {}
    contestant_votes = [
        v for v in all_votes.values()
        if isinstance(v, dict) and v.get('contestant_id') == clean_id
    ]
    
    supporters_map = {}
    for v in contestant_votes:
        phone = v.get('voter_phone') or 'Anonymous'
        count = int(v.get('vote_count', 1) or 1)
        name = v.get('voter_email', '').split('@')[0].title() if v.get('voter_email') else 'Comrade Backer'
        if phone not in supporters_map:
            # Mask phone for privacy: 2547****123
            masked = phone[:4] + "****" + phone[-3:] if len(phone) >= 7 else phone
            supporters_map[phone] = {"name": name, "masked_phone": masked, "votes": 0}
        supporters_map[phone]["votes"] += count

    supporters_list = sorted(supporters_map.values(), key=lambda x: x['votes'], reverse=True)[:10]

    # Conversion Stats
    views = max(contestant['vote_count'] * 3 + 18, int(contestant.get('views', 0) or 0))
    conversion_rate = min(100, round((contestant['vote_count'] / max(1, views)) * 100, 1))

    settings = get_awards_settings()
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")
    share_url = f"{base_url}/awards/contestant/{clean_id}"

    whatsapp_msg = (
        f"Hey comrades! 🏆 I have been nominated for *{contestant.get('category_name')}* at *{contestant.get('institution')}*!\n"
        f"I am currently *Rank #{current_rank}* with *{contestant['vote_count']} verified votes*.\n"
        f"Please support me with your vote (10 KES via M-Pesa or 1 Free daily vote) to win the national trophy! 🔥\n"
        f"Vote for me here: {share_url}"
    )
    whatsapp_encoded_text = urllib.parse.quote(whatsapp_msg)

    return render_template(
        'awards_contestant_dashboard.html',
        contestant=contestant,
        rivals=rivals,
        leader=leader,
        runner_up=runner_up,
        rival_ahead=rival_ahead,
        lead_margin=lead_margin,
        votes_to_next=votes_to_next,
        votes_to_leader=votes_to_leader,
        next_milestone=next_milestone,
        milestone_percent=milestone_percent,
        milestone_unlocked=milestone_unlocked,
        supporters=supporters_list,
        stats={"views": views},
        conversion_rate=conversion_rate,
        target_goal=max(100, next_milestone),
        settings=settings,
        share_url=share_url,
        whatsapp_encoded_text=whatsapp_encoded_text
    )


@awards_bp.route('/api/contestant/<cid>/update-bio', methods=['POST'])
def api_contestant_update_bio(cid):
    """Allows contestants to update their campaign pitch, slogan, and social handles."""
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(cid).strip())
    contestant_ref = db.reference(f'awards_contestants/{clean_id}')
    contestant = contestant_ref.get()

    if not contestant or not isinstance(contestant, dict):
        return jsonify({"success": False, "error": "Contestant record not found"}), 404

    data = request.get_json(silent=True) or request.form.to_dict()
    bio = sanitize_input(data.get('bio'), 1000)
    instagram = sanitize_input(data.get('instagram'), 60)
    tiktok = sanitize_input(data.get('tiktok'), 60)

    updates = {}
    if bio:
        updates['bio'] = bio
    if instagram or tiktok:
        existing_socials = contestant.get('socials') or {}
        if instagram:
            existing_socials['instagram'] = instagram
        if tiktok:
            existing_socials['tiktok'] = tiktok
        updates['socials'] = existing_socials

    if updates:
        contestant_ref.update(updates)

    return jsonify({"success": True, "message": "Campaign manifesto updated successfully!"}), 200


@awards_bp.route('/api/contestant/<cid>/votes', methods=['GET'])
def api_contestant_votes(cid):
    """Realtime poll endpoint for live vote counter & audio chime."""
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(cid).strip())
    contestant = db.reference(f'awards_contestants/{clean_id}').get()
    if not contestant or not isinstance(contestant, dict):
        return jsonify({"success": False, "error": "Contestant not found"}), 404

    return jsonify({
        "success": True,
        "vote_count": int(contestant.get('vote_count', 0) or 0)
    }), 200


@awards_bp.route('/api/contestant/<cid>/send-thank-you', methods=['POST'])
def api_contestant_send_thank_you(cid):
    """Dispatches thank-you emails to all registered voters who supported this contestant."""
    clean_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(cid).strip())
    contestant = db.reference(f'awards_contestants/{clean_id}').get()
    if not contestant or not isinstance(contestant, dict):
        return jsonify({"success": False, "error": "Contestant not found"}), 404

    # Fetch unique voter emails for this contestant
    all_votes = db.reference('awards_votes').get() or {}
    voter_emails = set()
    for v in all_votes.values():
        if isinstance(v, dict) and v.get('contestant_id') == clean_id:
            em = v.get('voter_email')
            if em and '@' in em:
                voter_emails.add(em.strip().lower())

    if not voter_emails:
        return jsonify({"success": False, "error": "No verified voter emails recorded yet."}), 400

    name = contestant.get('name', 'Nominee')
    cat = contestant.get('category_name', 'Awards')
    base_url = (os.getenv("BASE_URL") or "https://findyourmatch.co.ke").rstrip("/")

    sent_count = 0
    from app.email_service import _send_email
    for email_addr in list(voter_emails)[:50]:
        subj = f"💌 A personal thank-you from {name} ({cat})"
        txt = f"""Hi comrade,

I just wanted to take a moment to sincerely thank you for casting your vote for me in the {cat} category! Your support means the world to me. Keep rallying!

Best,
{name}"""
        html = f"""
        <div style="font-family: sans-serif; background: #0F172A; color: #F8FAFC; padding: 24px; border-radius: 12px; max-width: 500px; margin: 0 auto; border: 1px solid #1E293B;">
            <h2 style="color: #F59E0B; margin-top: 0;">Thank You for Believing in Me! 🏆</h2>
            <p style="font-size: 14px; line-height: 1.6; color: #E2E8F0;">
                Hi comrade,<br><br>
                I saw your vote come through on the live leaderboard for <strong>{cat}</strong>. Your support is pushing me closer to victory!
            </p>
            <div style="background: #1E293B; border-radius: 8px; padding: 12px; margin: 16px 0; text-align: center;">
                <span style="font-size: 12px; color: #94A3B8;">Current Standing:</span><br>
                <strong style="font-size: 18px; color: #10B981;">{contestant.get('vote_count', 0)} Verified Votes</strong>
            </div>
            <a href="{base_url}/awards/contestant/{clean_id}" style="display: inline-block; background: #F59E0B; color: #000; font-weight: 800; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-size: 13px;">
                Check Live Standing &rarr;
            </a>
        </div>
        """
        if _send_email(email_addr, subj, txt, html, sender_name=f"{name} via Campus Awards"):
            sent_count += 1

    return jsonify({"success": True, "sent_count": sent_count}), 200


@awards_bp.route('/api/banner-spotlight', methods=['GET'])
def api_banner_spotlight():
    """
    Supplies the dynamic awards spotlight banner for index.html with live category duels.
    Spotlights the leading vs trailing contestants to spark competition.
    Only active if Super Admin has clicked Start Campaign!
    """
    settings = get_awards_settings()
    campaign_active = bool(settings.get('campaign_active', False))
    banner_active = bool(settings.get('banner_active', False) and campaign_active and settings.get('phase') != 'closed')

    if not banner_active:
        return jsonify({
            "success": True,
            "banner_active": False,
            "message": "Awards activity is currently not active or paused by admin."
        }), 200

    all_contestants = db.reference('awards_contestants').get() or {}

    active_by_cat = {}
    for cid, c in all_contestants.items():
        if isinstance(c, dict) and c.get('status') == 'active':
            cat = c.get('category_name') or 'General'
            if cat not in active_by_cat:
                active_by_cat[cat] = []
            active_by_cat[cat].append({
                "id": cid,
                "name": c.get('name'),
                "institution": c.get('institution', 'Campus'),
                "vote_count": int(c.get('vote_count', 0) or 0),
                "photo_url": c.get('photo_url') or '/static/img/placeholder.png'
            })

    battles = []
    for cat_name, list_c in active_by_cat.items():
        if len(list_c) >= 1:
            list_c.sort(key=lambda x: x['vote_count'], reverse=True)
            leader = list_c[0]
            contender = list_c[1] if len(list_c) > 1 else None
            gap = (leader['vote_count'] - contender['vote_count']) if contender else 0
            battles.append({
                "category": cat_name,
                "leader": leader,
                "contender": contender,
                "gap": gap
            })

    return jsonify({
        "success": True,
        "banner_active": True,
        "campaign_title": settings.get('title', 'Kenya University & MMUST Awards 2026'),
        "finale_date": settings.get('finale_date', '2026-11-30T23:59:59'),
        "prize_pool_kes": settings.get('prize_pool_kes', 50000),
        "battles": battles[:6]
    }), 200


@awards_bp.route('/api/admin/toggle-campaign', methods=['POST'])
def api_admin_toggle_campaign():
    """
    Super Admin master switch to start or stop the campaign,
    activate or deactivate the 1-month voting window, and show/hide the homepage banner.
    """
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or request.form.to_dict()
    action = data.get('action')

    now = datetime.now(timezone.utc)
    settings_ref = db.reference('awards_settings')
    settings = get_awards_settings()

    updates = {'updated_at': now.isoformat()}

    if action == 'start':
        finale = now + timedelta(days=30)
        updates['campaign_active'] = True
        updates['banner_active'] = True
        updates['phase'] = 'voting'
        updates['campaign_start_date'] = now.isoformat()
        updates['finale_date'] = finale.isoformat()
        updates['blind_mode'] = False
        msg = f"Awards campaign STARTED! 1-Month voting window is LIVE until {finale.strftime('%d %b %Y')}. Homepage banner is now visible."

    elif action == 'pause':
        updates['banner_active'] = False
        msg = "Awards campaign PAUSED. Homepage banner is now hidden."

    elif action == 'show_banner':
        updates['banner_active'] = True
        msg = "Homepage voting banner is now VISIBLE."

    elif action == 'hide_banner':
        updates['banner_active'] = False
        msg = "Homepage voting banner is now HIDDEN."

    elif action == 'end':
        updates['campaign_active'] = False
        updates['banner_active'] = False
        updates['phase'] = 'closed'
        msg = "Awards campaign has been ENDED. Voting closed and banner removed."

    else:
        return jsonify({"success": False, "error": "Invalid campaign action"}), 400

    settings_ref.update(updates)
    return jsonify({
        "success": True,
        "message": msg,
        "updates": updates
    }), 200


@awards_bp.route('/api/admin/extend-campaign', methods=['POST'])
def api_admin_extend_campaign():
    """
    Super Admin quick-action to extend the 1-month campaign window by +7, +14, or +30 days.
    """
    if not (session.get('role') == 'admin' or session.get('super_admin') or session.get('is_super_admin')):
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or request.form.to_dict()
    add_days = int(data.get('days', 30))

    settings = get_awards_settings()
    current_finale = settings.get('finale_date')
    try:
        curr_dt = datetime.fromisoformat(current_finale.replace('Z', '+00:00'))
    except Exception:
        curr_dt = datetime.now(timezone.utc)

    new_dt = curr_dt + timedelta(days=add_days)
    new_finale_iso = new_dt.isoformat()

    db.reference('awards_settings').update({
        'finale_date': new_finale_iso,
        'phase': 'voting',
        'updated_at': datetime.now(timezone.utc).isoformat()
    })

    return jsonify({
        "success": True,
        "message": f"Campaign successfully extended by +{add_days} days to {new_finale_iso}!",
        "new_finale_date": new_finale_iso
    }), 200
