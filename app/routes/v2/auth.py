import re
import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from app.database import db, delete_user_account

# Import your email service
from app.email_service import send_verification_email

auth_v2_bp = Blueprint('auth_v2', __name__, url_prefix='/api/v2/auth')

# Define East Africa Time (UTC+3)
EAT = timezone(timedelta(hours=3))

# --- REGEX PATTERNS ---
# MMUST specific pattern
MMUST_REG_PATTERN = r"^[A-Z]{2,4}/[A-Z]/\d{2}-\d{4,5}/\d{4}$"
# Generic pattern for other institutions (at least some alphanumeric and separators)
GENERIC_REG_PATTERN = r"^[A-Z0-9/-]{5,30}$"
EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

def hash_family_name(name):
    """Encrypts family names so they are never stored as plain text."""
    if not name:
        return None
    clean_name = name.strip().lower()
    return hashlib.sha256(clean_name.encode('utf-8')).hexdigest()

def calculate_account_expiry(reg_number, institution="MMUST"):
    """
    Parses the Registration Number to determine the account expiry date.
    """
    try:
        if institution == "MMUST":
            parts = reg_number.strip().upper().split('/')
            if len(parts) >= 4:
                prefix = parts[0]
                start_year = int(parts[-1])
                
                if prefix.startswith('MED'):
                    duration = 6
                elif prefix in ['MIE', 'ECE', 'CSE', 'BTB']:
                    duration = 5
                else:
                    duration = 4
                    
                expiry_year = start_year + duration + 1
                return f"{expiry_year}-12-31T23:59:59"
    except Exception as e:
        print(f"Error parsing reg number for expiry: {e}")
        
    # Fallback to 5 years from today
    fallback_year = datetime.now(EAT).year + 5
    return f"{fallback_year}-12-31T23:59:59"

@auth_v2_bp.route('/signup', methods=['POST'])
def signup():
    """V2 Signup supporting multiple institutions and API versioning."""
    data = request.get_json() or request.form
    
    name = data.get('name')
    email = data.get('email', '').strip().lower()
    reg_number = data.get('reg_number')
    password = data.get('password')
    confirm_password = data.get('confirm_password')
    institution_type = data.get('institution_type', 'University')
    institution_name = data.get('institution_name', 'MMUST')
    is_student = data.get('is_student', True)
    
    # Optional fields
    age = int(data.get('age', 18))
    gender = data.get('gender')
    religion = data.get('religion')
    bio = data.get('bio', f'Hey! I am a student at {institution_name}.')
    ref_code = data.get('ref_code', '').strip() or session.get('referred_by', '')
    
    # 1. Basic Validations
    if not password or len(password) < 6:
        return jsonify({"status": "error", "message": "Password must be at least 6 characters."}), 400
    if password != confirm_password:
        return jsonify({"status": "error", "message": "Passwords do not match."}), 400
    if not email or not re.match(EMAIL_PATTERN, email):
        return jsonify({"status": "error", "message": "Please enter a valid email address."}), 400

    # 2. Institution-aware Reg Number Validation
    if reg_number:
        reg_number = reg_number.strip().upper()
        if institution_name == "MMUST":
            if not re.match(MMUST_REG_PATTERN, reg_number):
                return jsonify({"status": "error", "message": "Invalid MMUST Reg Format. Use: SAB/B/01-04774/2023"}), 400
        else:
            if not re.match(GENERIC_REG_PATTERN, reg_number):
                return jsonify({"status": "error", "message": "Invalid Registration Number format."}), 400
    else:
        # If not a student or no reg number, maybe generate a random ID
        if is_student:
             return jsonify({"status": "error", "message": "Registration Number is required for students."}), 400
        reg_number = f"EXT-{uuid.uuid4().hex[:8].upper()}"

    # 3. Check if user already exists
    safe_id = reg_number.replace('/', '_')
    existing_user = db.reference(f'profiles/{safe_id}').get()
    
    if existing_user and existing_user.get('is_verified'):
        return jsonify({"status": "error", "message": "This account is already registered. Try logging in."}), 400

    # 4. Create Profile
    hashed_password = generate_password_hash(password)
    expiry_date = calculate_account_expiry(reg_number, institution_name)
    created_at = datetime.now(EAT).isoformat()
    otp_code = random.randint(100000, 999999)
    
    referral_code = f"FYM-{name.split(' ')[0].upper()[:5]}-{''.join(random.choices(re.sub(r'[^A-Z0-9]', '', 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'), k=4))}"
    wingman_code = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=6))

    try:
        user_ref = db.reference(f'profiles/{safe_id}')
        user_ref.set({
            'id': safe_id,
            'name': name,
            'email': email,
            'reg_number': reg_number,
            'institution_name': institution_name,
            'institution_type': institution_type,
            'is_student': is_student,
            'password': hashed_password,
            'account_expiry': expiry_date,
            'created_at': created_at,
            'failed_attempts': 0,
            'is_locked': False,
            'age': age,
            'gender': gender,
            'religion': religion,
            'img': "https://via.placeholder.com/400",
            'bio': bio,
            'is_verified': False,
            'verification_code': str(otp_code),
            'referred_by': ref_code,
            'referral_code': referral_code,
            'wingman_code': wingman_code,
            'api_version': 'v2'
        })
        
        send_verification_email(email, name, otp_code)
        
        session['temp_user_id'] = safe_id
        session['temp_user_email'] = email
        
        return jsonify({
            "status": "success", 
            "message": f"Verification code sent to {email}.",
            "api_version": "v2"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@auth_v2_bp.route('/login', methods=['POST'])
def login():
    """V2 Login with enhanced security and versioning."""
    data = request.get_json() or request.form
    email = data.get('email', '').strip().lower()
    reg_number = data.get('reg_number')
    password = data.get('password')
    
    if not (email and reg_number and password):
        return jsonify({"status": "error", "message": "Missing credentials."}), 400
        
    safe_id = reg_number.strip().upper().replace('/', '_')
    
    try:
        user_ref = db.reference(f'profiles/{safe_id}')
        user = user_ref.get()
        
        if not user or user.get('email') != email:
            return jsonify({"status": "error", "message": "Invalid email, ID, or password."}), 401

        if user.get('is_locked'):
            return jsonify({"status": "error", "message": "Account locked. Please reset your password."}), 403

        if check_password_hash(user.get('password', ''), password):
            if not user.get('is_verified'):
                session['temp_user_id'] = safe_id
                session['temp_user_email'] = user.get('email')
                return jsonify({"status": "pending_verification", "message": "Account not verified."}), 200

            user_ref.update({'failed_attempts': 0})
            
            session['user_id'] = safe_id
            session['user_name'] = user.get('name')
            session['user_email'] = user.get('email')
            session['api_version'] = 'v2'
            
            return jsonify({
                "status": "success", 
                "message": f"Welcome back, {user['name']}!",
                "user": {
                    "id": safe_id,
                    "name": user.get('name'),
                    "institution": user.get('institution_name')
                },
                "api_version": "v2"
            })
        else:
            attempts = user.get('failed_attempts', 0) + 1
            user_ref.update({'failed_attempts': attempts})
            if attempts >= 5:
                user_ref.update({'is_locked': True})
            return jsonify({"status": "error", "message": "Invalid credentials."}), 401
            
    except Exception as e:
        return jsonify({"status": "error", "message": "Server error."}), 500
