import os
import uuid
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from app.database import (
    create_sponsor_profile, get_sponsor_profile, get_all_sponsors, get_sponsor_by_email,
    get_all_profiles, grant_sponsors_room_access, log_sponsors_room_payment,
    has_sponsors_room_access, update_sponsor_profile
)
from app.payments import initiate_stk_push
from app.pricing import get_sponsor_registration_fee, get_sponsors_room_fee, is_sponsors_room_free
from app.email_service import send_sponsor_welcome_email, send_sponsor_room_welcome_email

sponsors_bp = Blueprint('sponsors', __name__)
EAT = timezone(timedelta(hours=3))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('account_type') != 'sponsor':
            flash("Please log in as a sponsor.", "warning")
            return redirect(url_for('sponsors.sponsor_login'))
        return f(*args, **kwargs)
    return decorated_function

def student_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('account_type') == 'sponsor':
            flash("Please log in as a student.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ==========================================
# SPONSOR ACCOUNT (AUTH & DASHBOARD)
# ==========================================

@sponsors_bp.route('/sponsor/register', methods=['GET', 'POST'])
def sponsor_register():
    if request.method == 'GET':
        fee = get_sponsor_registration_fee('any')
        return render_template('sponsor_register.html', fee=fee)

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password')
    gender = request.form.get('gender')
    age = request.form.get('age')
    county = request.form.get('county')
    bio = request.form.get('bio', '')

    if get_sponsor_by_email(email):
        flash("Email is already registered as a sponsor.", "error")
        return redirect(url_for('sponsors.sponsor_register'))

    sponsor_id = f"spon_{uuid.uuid4().hex[:16]}"
    now_eat = datetime.now(EAT).isoformat()
    
    sponsor_data = {
        'id': sponsor_id,
        'name': name,
        'email': email,
        'phone': phone,
        'password_hash': generate_password_hash(password),
        'gender': gender,
        'age': age,
        'county': county,
        'bio': bio,
        'is_active': False,
        'is_verified': False,
        'created_at': now_eat
    }

    # Save to database immediately
    create_sponsor_profile(sponsor_id, sponsor_data)
    
    # Log them in
    session['user_id'] = sponsor_id
    session['account_type'] = 'sponsor'
    session['gender'] = gender
    
    from flask import make_response
    resp = make_response(redirect(url_for('sponsors.sponsor_dashboard')))
    resp.set_cookie('account_type_pref', 'sponsor', max_age=31536000)

    # Initiate STK Push automatically
    fee = get_sponsor_registration_fee(gender)
    base_url = os.getenv("BASE_URL", request.host_url.rstrip('/'))
    callback_url = f"{base_url}/api/v2/sponsor/payment/callback"
    
    stk_res = initiate_stk_push(phone, fee, sponsor_id, callback_url, "Sponsor Registration")
    
    if "error" not in stk_res:
        session['checkout_id'] = stk_res.get("CheckoutRequestID")
        session['payment_intent'] = 'sponsor_register'
    
    return resp


@sponsors_bp.route('/api/v2/sponsor/payment/callback', methods=['POST'])
def sponsor_payment_callback():
    from flask import current_app
    # Because CSRF exempt is required for callbacks, we'll exempt it in main.py
    data = request.json or {}
    try:
        stk_callback = data.get('Body', {}).get('stkCallback', {})
        result_code = str(stk_callback.get('ResultCode', ''))
        checkout_id = stk_callback.get('CheckoutRequestID')
        
        if result_code == "0":
            # Find the pending session data... 
            # In a real webhook, we'd store pending users in a DB table, but here we can just update a "payments" log
            # Since the user's browser polls /api/payment/status, we rely on the client session for simplicity in this demo structure.
            pass
    except Exception as e:
        pass
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


@sponsors_bp.route('/api/v2/sponsor/finalize-registration', methods=['POST'])
@login_required
def sponsor_finalize_registration():
    """Called by paywall.html when polling confirms payment."""
    user_id = session.get('user_id')
    checkout_id = session.get('checkout_id')
    
    if not checkout_id or not user_id:
        return jsonify({"success": False, "error": "No pending payment found."})
        
    sponsor = get_sponsor_profile(user_id)
    if not sponsor:
        return jsonify({"success": False, "error": "Profile not found."})

    from app.payments import check_payment_status
    status = check_payment_status(checkout_id)
    
    if status.get("status") == "PAID":
        update_sponsor_profile(user_id, {'is_active': True})
        send_sponsor_welcome_email(sponsor['email'], sponsor['name'])
        
        return jsonify({"success": True, "status": "PAID"})
        
    return jsonify({"success": False, "status": status.get("status")})

@sponsors_bp.route('/api/v2/sponsor/trigger-payment', methods=['POST'])
@login_required
def trigger_sponsor_payment():
    """Called by paywall.html if a sponsor needs to manually retry STK push."""
    data = request.get_json() or {}
    phone = data.get('phone_number')
    sponsor = get_sponsor_profile(session.get('user_id'))
    
    if not phone or not sponsor:
        return jsonify({"success": False, "message": "Invalid request."})
        
    fee = get_sponsor_registration_fee(sponsor.get('gender'))
    base_url = os.getenv("BASE_URL", request.host_url.rstrip('/'))
    callback_url = f"{base_url}/api/v2/sponsor/payment/callback"
    
    stk_res = initiate_stk_push(phone, fee, sponsor['id'], callback_url, "Sponsor Registration")
    if "error" in stk_res:
        return jsonify({"success": False, "message": stk_res["error"]})
        
    session['checkout_id'] = stk_res.get("CheckoutRequestID")
    return jsonify({"success": True})


@sponsors_bp.route('/sponsor/login', methods=['GET', 'POST'])
def sponsor_login():
    if request.method == 'GET':
        return render_template('sponsor_login.html')
        
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    
    sponsor = get_sponsor_by_email(email)
    if sponsor and check_password_hash(sponsor.get('password_hash', ''), password):
        session['user_id'] = sponsor['id']
        session['account_type'] = 'sponsor'
        session['gender'] = sponsor.get('gender')
        session.permanent = True
        
        from flask import make_response
        resp = make_response(redirect(url_for('sponsors.sponsor_dashboard')))
        resp.set_cookie('account_type_pref', 'sponsor', max_age=31536000)
        return resp
        
    flash("Invalid sponsor credentials.", "error")
    return redirect(url_for('sponsors.sponsor_login'))


@sponsors_bp.route('/sponsor/dashboard')
@login_required
def sponsor_dashboard():
    sponsor = get_sponsor_profile(session['user_id'])
    
    if not sponsor.get('is_active'):
        fee = get_sponsor_registration_fee(sponsor.get('gender'))
        phone = sponsor.get('phone', '')
        checkout_id = session.get('checkout_id')
        # Show paywall directly on dashboard if inactive
        return render_template('paywall.html', amount=fee, phone=phone, checkout_id=checkout_id, intent='sponsor_register')
        
    # Sponsors can see all verified students matching their preference (or all)
    all_students = get_all_profiles()
    active_students = [s for s in all_students if s.get('is_verified') and not s.get('is_banned')]
    return render_template('sponsor_dashboard.html', sponsor=sponsor, students=active_students)


# ==========================================
# SPONSORS ROOM (STUDENT ACCESS)
# ==========================================

@sponsors_bp.route('/sponsors-room')
@student_login_required
def sponsors_room():
    user_id = session.get('user_id')
    
    # 1. Check access
    if not has_sponsors_room_access(user_id):
        # Redirect to payment page
        gender = session.get('gender', 'male')
        fee = get_sponsors_room_fee(gender)
        
        if fee == 0:
            # Auto-grant female students
            grant_sponsors_room_access(user_id, days=30)
            flash("Sponsors Room unlocked for free!", "success")
            return redirect(url_for('sponsors.sponsors_room'))
            
        return render_template('sponsors_room_paywall.html', fee=fee)
        
    # 2. Render room
    sponsors = get_all_sponsors(verified_only=True)
    return render_template('sponsors_room.html', sponsors=sponsors)


@sponsors_bp.route('/api/v2/sponsor-room/pay', methods=['POST'])
@student_login_required
def pay_sponsor_room():
    user_id = session.get('user_id')
    gender = session.get('gender', 'male')
    phone = request.form.get('phone', '').strip()
    
    fee = get_sponsors_room_fee(gender)
    if fee == 0:
        return jsonify({"success": False, "error": "Room is free for you."})
        
    base_url = os.getenv("BASE_URL", request.host_url.rstrip('/'))
    callback_url = f"{base_url}/api/v2/sponsor-room/payment/callback"
    
    stk_res = initiate_stk_push(phone, fee, user_id, callback_url, "Sponsors Room")
    if "error" in stk_res:
        return jsonify({"success": False, "error": stk_res["error"]})
        
    checkout_id = stk_res.get("CheckoutRequestID")
    session['checkout_id'] = checkout_id
    session['payment_intent'] = 'sponsor_room'
    
    return jsonify({"success": True, "checkout_id": checkout_id})


@sponsors_bp.route('/api/v2/sponsor-room/finalize', methods=['POST'])
@student_login_required
def finalize_sponsor_room():
    user_id = session.get('user_id')
    checkout_id = session.get('checkout_id')
    
    if not checkout_id:
        return jsonify({"success": False})
        
    from app.payments import check_payment_status
    status = check_payment_status(checkout_id)
    
    if status.get("status") == "PAID":
        gender = session.get('gender', 'male')
        fee = get_sponsors_room_fee(gender)
        
        grant_sponsors_room_access(user_id, days=30)
        log_sponsors_room_payment(user_id, fee, checkout_id)
        
        # Send welcome email (async ideally, but inline here for simplicity)
        from app.database import db
        profile = db.reference(f'profiles/{user_id}').get()
        if profile and profile.get('email'):
            send_sponsor_room_welcome_email(profile['email'], profile.get('name', 'User'))
            
        return jsonify({"success": True, "status": "PAID"})
        
    return jsonify({"success": True, "status": status.get("status")})
