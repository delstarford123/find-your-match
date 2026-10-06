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
    session['pending_sponsor'] = {
        'id': sponsor_id,
        'name': name,
        'email': email,
        'phone': phone,
        'password_hash': generate_password_hash(password),
        'gender': gender,
        'age': age,
        'county': county,
        'bio': bio,
    }

    # Initiate STK Push
    fee = get_sponsor_registration_fee(gender)
    base_url = os.getenv("BASE_URL", request.host_url.rstrip('/'))
    callback_url = f"{base_url}/api/v2/sponsor/payment/callback"
    
    stk_res = initiate_stk_push(phone, fee, sponsor_id, callback_url, "Sponsor Registration")
    
    if "error" in stk_res:
        flash(stk_res["error"], "error")
        return redirect(url_for('sponsors.sponsor_register'))
        
    checkout_id = stk_res.get("CheckoutRequestID")
    session['checkout_id'] = checkout_id
    session['payment_intent'] = 'sponsor_register'
    
    return render_template('paywall.html', amount=fee, phone=phone, checkout_id=checkout_id, intent='sponsor_register')


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
def sponsor_finalize_registration():
    """Called by paywall.html when polling confirms payment."""
    pending = session.get('pending_sponsor')
    if not pending:
        return jsonify({"success": False, "error": "No pending registration found."})
        
    success = create_sponsor_profile(pending['id'], pending)
    if success:
        send_sponsor_welcome_email(pending['email'], pending['name'])
        session['user_id'] = pending['id']
        session['account_type'] = 'sponsor'
        session.pop('pending_sponsor', None)
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Failed to create profile."})


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
        return redirect(url_for('sponsors.sponsor_dashboard'))
        
    flash("Invalid sponsor credentials.", "error")
    return redirect(url_for('sponsors.sponsor_login'))


@sponsors_bp.route('/sponsor/dashboard')
@login_required
def sponsor_dashboard():
    sponsor = get_sponsor_profile(session['user_id'])
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
