"""
app/routes/v3/auth.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FYM API v3 — Passwordless Registration Number Auth
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
New users: email + password only (no registration number needed).
Legacy v1/v2 users: continue using reg number, optionally upgrade.

Endpoints:
  POST /api/v3/auth/signup   → New account (no reg number)
  POST /api/v3/auth/login    → Email + password (no reg number)
  POST /api/v3/auth/upgrade  → Legacy user migrates to v3
"""

import re
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, request, session, jsonify

from app.database import db
from app.email_service import send_verification_email

# ── Blueprint ─────────────────────────────────────────────────────────────────
auth_v3_bp = Blueprint('auth_v3', __name__, url_prefix='/api/v3/auth')

# ── Constants ─────────────────────────────────────────────────────────────────
EAT = timezone(timedelta(hours=3))
EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
PLACEHOLDER_IMAGES = {
    "https://via.placeholder.com/400",
    "https://placehold.co/400",
    "",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_uid() -> str:
    """Generates a stable, safe Firebase key for v3 users."""
    return f"uid_{uuid.uuid4().hex}"


def _generate_referral_code(name: str) -> str:
    clean = re.sub(r'[^A-Z0-9]', '', name.upper())[:5] or "FYM"
    suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"FYM-{clean}-{suffix}"


def _lookup_user_by_email(email: str):
    """
    Scans all profiles to find a user by email.
    Returns (user_id, user_data) or (None, None).
    Searches both legacy (reg-number keyed) and v3 (uid_*) profiles.
    """
    try:
        all_profiles = db.reference('profiles').get() or {}
        for uid, data in all_profiles.items():
            if data and data.get('email', '').lower() == email.lower():
                return uid, data
    except Exception as e:
        print(f"[v3 auth] email lookup error: {e}")
    return None, None


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_v3_bp.route('/signup', methods=['POST'])
def signup():
    """
    v3 Signup — no registration number required.
    Required fields: name, email, password, confirm_password, gender, age
    Optional: phone, bio, ref_code, institution_name
    """
    data = request.get_json(silent=True) or request.form

    name             = (data.get('name') or '').strip()
    email            = (data.get('email') or '').strip().lower()
    password         = data.get('password') or ''
    confirm_password = data.get('confirm_password') or ''
    gender           = data.get('gender') or ''
    age_raw          = data.get('age', 18)
    phone            = (data.get('phone') or '').strip()
    bio              = (data.get('bio') or f'Hey! I just joined Find Your Match.').strip()
    ref_code         = (data.get('ref_code') or session.get('referred_by', '')).strip()
    institution_name = (data.get('institution_name') or 'General').strip()
    religion         = data.get('religion') or ''

    # ── Validation ────────────────────────────────────────────────────────────
    if not name or len(name) < 2:
        return jsonify({"status": "error", "message": "Please enter your full name."}), 400

    if not email or not re.match(EMAIL_PATTERN, email):
        return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400

    if not password or len(password) < 6:
        return jsonify({"status": "error", "message": "Password must be at least 6 characters."}), 400

    if password != confirm_password:
        return jsonify({"status": "error", "message": "Passwords do not match."}), 400

    if not gender:
        return jsonify({"status": "error", "message": "Please select your gender."}), 400

    try:
        age = int(age_raw)
        if age < 16 or age > 60:
            return jsonify({"status": "error", "message": "Please enter a valid age (16–60)."}), 400
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Please enter a valid age."}), 400

    # ── Duplicate email check ─────────────────────────────────────────────────
    existing_uid, existing_user = _lookup_user_by_email(email)
    if existing_uid and existing_user and existing_user.get('is_verified'):
        return jsonify({"status": "error", "message": "An account with this email already exists. Please log in."}), 409

    # ── Create account ────────────────────────────────────────────────────────
    uid             = _generate_uid()
    hashed_password = generate_password_hash(password)
    otp_code        = random.randint(100000, 999999)
    referral_code   = _generate_referral_code(name)
    wingman_code    = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    created_at      = datetime.now(EAT).isoformat()

    profile_data = {
        'id':             uid,
        'name':           name,
        'email':          email,
        'phone':          phone,
        'password':       hashed_password,
        'gender':         gender,
        'age':            age,
        'bio':            bio,
        'religion':       religion,
        'institution':    institution_name,
        'img':            '',           # Empty = not yet set; triggers profile wizard
        'is_verified':    False,
        'is_locked':      False,
        'is_paid':        False,
        'failed_attempts': 0,
        'api_version':    'v3',         # Key flag: v3 user — no reg number
        'reg_number':     None,         # Explicitly null for v3 users
        'referral_code':  referral_code,
        'wingman_code':   wingman_code,
        'referred_by':    ref_code,
        'referrals_count': 0,
        'free_weeks_earned': 0,
        'verification_code': str(otp_code),
        'created_at':     created_at,
        'profile_complete': False,      # Will be True once img + phone added
        'account_expiry': f"{datetime.now(EAT).year + 10}-12-31T23:59:59",
    }

    try:
        db.reference(f'profiles/{uid}').set(profile_data)
        send_verification_email(email, name, otp_code)

        session['temp_user_id']    = uid
        session['temp_user_email'] = email

        return jsonify({
            "status":      "success",
            "message":     f"Verification code sent to {email}. Please check your inbox!",
            "api_version": "v3",
            "user_id":     uid,
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Could not create account: {str(e)}"}), 500


@auth_v3_bp.route('/login', methods=['POST'])
def login():
    """
    v3 Login — email + password only.
    Also accepts legacy v1/v2 users who have been migrated or who have
    email-based login. Falls back gracefully.
    """
    data     = request.get_json(silent=True) or request.form
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"status": "error", "message": "Email and password are required."}), 400

    # Find user by email across all profiles
    uid, user = _lookup_user_by_email(email)

    if not uid or not user:
        return jsonify({"status": "error", "message": "No account found with this email address."}), 401

    # Account locked?
    if user.get('is_locked'):
        return jsonify({"status": "error", "message": "Account locked due to too many failed attempts. Please reset your password."}), 403

    # Verify password
    if not check_password_hash(user.get('password', ''), password):
        attempts = user.get('failed_attempts', 0) + 1
        update_data = {'failed_attempts': attempts}
        if attempts >= 5:
            update_data['is_locked'] = True
        db.reference(f'profiles/{uid}').update(update_data)
        return jsonify({"status": "error", "message": f"Incorrect password. {max(0, 5 - attempts)} attempt(s) remaining."}), 401

    # Email not yet verified?
    if not user.get('is_verified'):
        session['temp_user_id']    = uid
        session['temp_user_email'] = email
        return jsonify({"status": "pending_verification", "message": "Account not yet verified. Please check your email for the code."}), 200

    # ── Successful login ───────────────────────────────────────────────────────
    db.reference(f'profiles/{uid}').update({'failed_attempts': 0})

    session['user_id']      = uid
    session['user_name']    = user.get('name')
    session['user_email']   = user.get('email')
    session['user_img']     = user.get('img', '')
    session['api_version']  = 'v3'

    # Determine if this is a legacy user that can be upgraded
    is_legacy = user.get('api_version') in ('v1', 'v2', None) or bool(user.get('reg_number'))
    is_upgraded = user.get('api_version') == 'v3'

    # Check profile completeness
    img_ok   = bool(user.get('img')) and user.get('img') not in PLACEHOLDER_IMAGES
    phone_ok = bool(user.get('phone'))
    profile_complete = img_ok and phone_ok

    return jsonify({
        "status":           "success",
        "message":          f"Welcome back, {user.get('name', 'there')}!",
        "api_version":      "v3",
        "is_legacy_user":   is_legacy and not is_upgraded,
        "profile_complete": profile_complete,
        "missing_fields":   [] if profile_complete else (
            (["image"] if not img_ok else []) + (["phone"] if not phone_ok else [])
        ),
        "user": {
            "id":          uid,
            "name":        user.get('name'),
            "email":       email,
            "gender":      user.get('gender'),
            "institution": user.get('institution') or user.get('institution_name'),
        }
    }), 200


@auth_v3_bp.route('/upgrade', methods=['POST'])
def upgrade_legacy_account():
    """
    Migrates a legacy v1/v2 account to the v3 system.
    The user must already be logged in (session['user_id'] set).
    Sets api_version='v3' and clears reg_number dependency.
    """
    uid = session.get('user_id')
    if not uid:
        return jsonify({"status": "error", "message": "You must be logged in to upgrade."}), 401

    user = db.reference(f'profiles/{uid}').get()
    if not user:
        return jsonify({"status": "error", "message": "User not found."}), 404

    if user.get('api_version') == 'v3':
        return jsonify({"status": "info", "message": "Your account is already on the latest system."}), 200

    try:
        db.reference(f'profiles/{uid}').update({
            'api_version':  'v3',
            'upgraded_at':  datetime.now(EAT).isoformat(),
            'upgraded_from': user.get('api_version', 'v1'),
        })
        session['api_version'] = 'v3'

        return jsonify({
            "status":  "success",
            "message": "Your account has been successfully upgraded! You can now log in with just your email and password.",
            "api_version": "v3",
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Upgrade failed: {str(e)}"}), 500


@auth_v3_bp.route('/profile/check', methods=['GET'])
def check_profile():
    """
    Returns the current user's profile completion status.
    Used by the frontend to decide whether to show the completion wizard.
    """
    uid = session.get('user_id')
    if not uid:
        return jsonify({"status": "error", "message": "Not authenticated."}), 401

    user = db.reference(f'profiles/{uid}').get()
    if not user:
        return jsonify({"status": "error", "message": "Profile not found."}), 404

    img   = user.get('img', '')
    phone = user.get('phone', '')
    bio   = user.get('bio', '')
    name  = user.get('name', '')

    img_ok   = bool(img) and img not in PLACEHOLDER_IMAGES
    phone_ok = bool(phone) and len(str(phone)) >= 9
    bio_ok   = bool(bio) and len(bio) > 10
    name_ok  = bool(name) and len(name) >= 2

    missing = []
    if not img_ok:   missing.append("image")
    if not phone_ok: missing.append("phone")

    # Score out of 100
    checks   = [img_ok, phone_ok, bio_ok, name_ok]
    score    = int((sum(checks) / len(checks)) * 100)
    complete = img_ok and phone_ok  # Minimum required: image + phone

    return jsonify({
        "status":   "success",
        "complete": complete,
        "score":    score,
        "missing":  missing,
        "details": {
            "has_image": img_ok,
            "has_phone": phone_ok,
            "has_bio":   bio_ok,
            "has_name":  name_ok,
        }
    }), 200
