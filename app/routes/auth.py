import re
import hashlib
import random
import uuid
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.database import db, delete_user_account

# Import your email service
from app.email_service import send_verification_email

auth_bp = Blueprint('auth', __name__)

# Define East Africa Time (UTC+3)
EAT = timezone(timedelta(hours=3))

# --- REGEX PATTERNS ---
REG_PATTERN = r"^[A-Z]{2,4}/[A-Z]/\d{2}-\d{4,5}/\d{4}$"
EMAIL_PATTERN = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"

def hash_family_name(name):
    """Encrypts family names so they are never stored as plain text."""
    if not name:
        return None
    clean_name = name.strip().lower()
    return hashlib.sha256(clean_name.encode('utf-8')).hexdigest()

def calculate_account_expiry(reg_number):
    """
    Parses the MMUST Registration Number to determine the account expiry date.
    Format: PREFIX/MIDDLE/ID/YEAR (e.g., SAB/B/01-04774/2023)
    - Default: 4 years + 1 grace year = 5 years
    - MIE, ECE, CSE, BTB: 5 years + 1 grace year = 6 years
    - MED: 6 years + 1 grace year = 7 years
    Expires on December 31st of the expiry year.
    """
    try:
        parts = reg_number.strip().upper().split('/')
        if len(parts) >= 4:
            prefix = parts[0]
            start_year = int(parts[-1])
            
            # Determine base course duration
            if prefix.startswith('MED'):
                duration = 6
            elif prefix in ['MIE', 'ECE', 'CSE', 'BTB']:
                duration = 5
            else:
                duration = 4
                
            # Add 1 year grace period
            expiry_year = start_year + duration + 1
            
            # Return December 31st of the expiry year
            return f"{expiry_year}-12-31T23:59:59"
    except Exception as e:
        print(f"Error parsing reg number for expiry: {e}")
        
    # Fallback to 5 years from today if format is unrecognized
    fallback_year = datetime.now(EAT).year + 5
    return f"{fallback_year}-12-31T23:59:59"

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # 1. Grab all fields from the HTML form
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        reg_number = request.form.get('reg_number')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        bio = request.form.get('bio', 'Hey! I am using MMUST Dating AI.')
        
        # --- REFERRAL LOGIC: Check form first, then check session ---
        ref_code = request.form.get('ref_code', '').strip() or session.get('referred_by', '')
        
        # Expanded Fields
        age = int(request.form.get('age', 18))
        gender = request.form.get('gender')
        religion = request.form.get('religion')
        skip_pic = request.form.get('skip_pic') == 'on'

        # Family Tree Fields (Hashed immediately for privacy)
        father_surname = hash_family_name(request.form.get('father_surname'))
        mother_maiden = hash_family_name(request.form.get('mother_maiden'))

        # 2. Validation: Passwords
        if not password or len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return redirect(url_for('auth.signup'))
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for('auth.signup'))

        # 3. Validation: Reg Number Format
        if reg_number:
            reg_number = reg_number.strip().upper()
        
        if not reg_number or not re.match(REG_PATTERN, reg_number):
            flash("Invalid Reg Format. Use: SAB/B/01-04774/2023", "error")
            return redirect(url_for('auth.signup'))

        # 4. Validation: Normal Email Format
        if not email or not re.match(EMAIL_PATTERN, email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for('auth.signup'))

        # 5. Check if user already exists (Optimized O(1) Fetch)
        safe_reg_number = reg_number.replace('/', '_')
        existing_user = db.reference(f'profiles/{safe_reg_number}').get()
        
        if existing_user:
            flash("This Registration Number is already registered. Try logging in.", "error")
            return redirect(url_for('auth.login'))

        profile_img = "" if skip_pic else "https://via.placeholder.com/400"
        
        # 6. Hash Password and Calculate Expiry
        hashed_password = generate_password_hash(password)
        expiry_date = calculate_account_expiry(reg_number)

        # 7. GENERATE OTP & SAVE TO FIREBASE
        try:
            otp_code = random.randint(100000, 999999)
            
            user_ref = db.reference(f'profiles/{safe_reg_number}')
            user_ref.set({
                'id': safe_reg_number,
                'name': name,
                'email': email,
                'reg_number': reg_number,
                'password': hashed_password,        # 🔒 Securely hashed password
                'account_expiry': expiry_date,      # ⏳ Automated Deletion Date
                'failed_attempts': 0,               # 🛡️ Brute-force tracker
                'is_locked': False,                 # 🔒 Lockout status
                'age': age,
                'gender': gender,
                'religion': religion,
                'father_hash': father_surname,
                'mother_hash': mother_maiden,
                'img': profile_img,
                'bio': bio,
                'vibe_vector': [0.0, 0.0, 0.0, 0.0],
                'is_verified': False,            # User must verify via code
                'verification_code': str(otp_code), # Store code as string for exact matching
                'referred_by': ref_code          # Saves who invited them!
            })
            
            # Send the Email 
            send_verification_email(email, name, otp_code)
            
            # Create a TEMPORARY browser session
            session['temp_user_id'] = safe_reg_number
            session['temp_user_email'] = email
            
            flash(f"Verification code sent to {email}. Please check your inbox!", "success")
            return redirect(url_for('auth.verify_email'))
            
        except Exception as e:
            flash(f"Database error: {str(e)}", "error")
            return redirect(url_for('auth.signup'))

    return render_template('signup.html')


@auth_bp.route('/verify', methods=['GET', 'POST'])
def verify_email():
    """Handles the 6-digit OTP verification and grants Premium Rewards."""
    # Look for either a temporary session (just signed up) or full session
    user_id = session.get('temp_user_id') or session.get('user_id')
    
    if not user_id:
        flash("Session expired. Please log in again.", "warning")
        return redirect(url_for('auth.login'))

    user_ref = db.reference(f'profiles/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        return redirect(url_for('auth.signup'))

    # If already verified, fully log them in and send to the swipe deck
    if user_data.get('is_verified'):
        session['user_id'] = user_id
        session['user_name'] = user_data.get('name')
        session['user_email'] = user_data.get('email')
        session['user_img'] = user_data.get('img')
        session.pop('temp_user_id', None)
        return redirect(url_for('swipe'))

    if request.method == 'POST':
        entered_code = request.form.get('otp_code', '').strip()
        actual_code = str(user_data.get('verification_code'))

        if entered_code == actual_code:
            # 1. Prepare base update payload
            user_updates = {
                'is_verified': True,
                'verification_code': None 
            }
            
            now_eat = datetime.now(EAT)
            bonus_premium_days = 0  # Start with 0 free days
            
            # ====================================================
            # 2. CHECK FOR ADMIN "14-DAY FREE TRIAL" CAMPAIGN
            # ====================================================
            system_settings = db.reference('system_settings').get() or {}
            if system_settings.get('new_user_promo') == True:
                bonus_premium_days += 14  # Add 2 weeks free!
            
            # ====================================================
            # 3. VIP REFERRAL REWARD SYSTEM 
            # ====================================================
            referred_by_code = user_data.get('referred_by')
            if referred_by_code:
                try:
                    # Find the user who sent the invite link
                    referrers = db.reference('profiles').order_by_child('referral_code').equal_to(referred_by_code).get()
                    
                    if referrers:
                        referrer_id = list(referrers.keys())[0]
                        referrer_data = referrers[referrer_id]
                        
                        # A. Give the Referrer 1 Week Premium
                        new_count = referrer_data.get('referrals_count', 0) + 1
                        new_weeks = referrer_data.get('free_weeks_earned', 0) + 1
                        
                        ref_exp_str = referrer_data.get('subscription_expiry')
                        # If they already have premium, ADD 7 days to their current expiry
                        if ref_exp_str and datetime.fromisoformat(ref_exp_str) > now_eat.replace(tzinfo=None):
                            new_ref_exp = (datetime.fromisoformat(ref_exp_str) + timedelta(days=7)).isoformat()
                        else:
                            new_ref_exp = (now_eat + timedelta(days=7)).isoformat()

                        db.reference(f'profiles/{referrer_id}').update({
                            'referrals_count': new_count,
                            'free_weeks_earned': new_weeks,
                            'is_paid': True,
                            'subscription_expiry': new_ref_exp
                        })
                        
                        # B. Add 7 days to the New User's bonus pool
                        bonus_premium_days += 7
                        
                        # Clear the session code
                        session.pop('referred_by', None)
                        flash("VIP Invite Confirmed! You both get 1 Free Week of Premium! 🎉", "success")
                except Exception as e:
                    print(f"Error processing referral reward: {e}")

            # ====================================================
            # 4. APPLY ACCUMULATED FREE DAYS
            # ====================================================
            if bonus_premium_days > 0:
                user_updates['is_paid'] = True
                user_updates['subscription_expiry'] = (now_eat + timedelta(days=bonus_premium_days)).isoformat()
                user_updates['last_payment_receipt'] = f'SYSTEM_PROMO_{bonus_premium_days}_DAYS'

            # 5. Apply updates to the newly verified user
            user_ref.update(user_updates)
            
            # 6. Upgrade temporary session to a full, authorized session
            session['user_id'] = user_id
            session['user_name'] = user_data.get('name')
            session['user_email'] = user_data.get('email')
            session['user_img'] = user_data.get('img')
            session['user_religion'] = user_data.get('religion', 'Other')
            session.pop('temp_user_id', None)
            
            if not referred_by_code:
                if bonus_premium_days >= 14:
                    flash("Account verified! You've been granted a 14-Day Free Trial! 🚀", "success")
                else:
                    flash("Account verified successfully! Welcome to MMUST Dating AI.", "success")
                
            return redirect(url_for('swipe'))
        else:
            flash("Invalid code. Please check your email and try again.", "error")

    email_to_show = session.get('temp_user_email') or user_data.get('email')
    return render_template('verify.html', email=email_to_show)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        reg_number = request.form.get('reg_number')
        password = request.form.get('password')
        
        if email and reg_number and password:
            safe_reg_number = reg_number.strip().upper().replace('/', '_')
            
            # --- 🚨 CRITICAL FIX: PREVENT FIREBASE CRASH 🚨 ---
            invalid_chars = ['.', '#', '$', '[', ']']
            if any(char in safe_reg_number for char in invalid_chars):
                flash("Invalid Registration Number format.", "error")
                return redirect(url_for('auth.login'))

            try:
                # Optimized O(1) Fetch directly from the user's node
                user_ref = db.reference(f'profiles/{safe_reg_number}')
                user = user_ref.get()
                
                if user:
                    # 1. 🔒 SECURITY: Verify Email Matches Exactly!
                    if user.get('email') != email:
                        # Use a generic error so attackers don't know which part was wrong
                        flash("Incorrect Email, Registration Number, or Password.", "error")
                        return redirect(url_for('auth.login'))

                    # 2. CHECK AUTOMATED EXPIRY (Graduation + Grace Period)
                    expiry_str = user.get('account_expiry')
                    if expiry_str:
                        try:
                            expiry_date = datetime.fromisoformat(expiry_str)
                            if datetime.now(EAT).replace(tzinfo=None) > expiry_date:
                                # Auto-delete account if past grace period
                                delete_user_account(safe_reg_number)
                                flash("Your account has expired as you have passed your graduation grace period. All data has been deleted.", "error")
                                return redirect(url_for('auth.login'))
                        except Exception as e:
                            print(f"Expiry check error: {e}")

                    # 3. CHECK BRUTE FORCE LOCKOUT
                    if user.get('is_locked'):
                        flash("Account locked due to too many failed attempts. Please unlock it.", "error")
                        return redirect(url_for('auth.unlock_account'))

                    # 4. Security Check: Did they verify their OTP?
                    if not user.get('is_verified'):
                        session['temp_user_id'] = safe_reg_number
                        session['temp_user_email'] = user.get('email')
                        flash("Please verify your account to continue.", "warning")
                        return redirect(url_for('auth.verify_email'))

                    # 5. 🔒 VERIFY PASSWORD
                    if check_password_hash(user.get('password', ''), password):
                        # Success! Reset failed attempts
                        user_ref.update({'failed_attempts': 0})
                        
                        # Full Login Authorization
                        session['user_id'] = safe_reg_number
                        session['user_name'] = user.get('name')
                        session['user_email'] = user.get('email')
                        session['user_img'] = user.get('img')
                        session['user_religion'] = user.get('religion', 'Other') 
                        
                        flash(f"Welcome back, {user['name']}!", "success")
                        return redirect(url_for('swipe'))
                    else:
                        # Failed Password Attempt Handling
                        attempts = user.get('failed_attempts', 0) + 1
                        if attempts >= 4:
                            user_ref.update({'failed_attempts': attempts, 'is_locked': True})
                            flash("Account locked due to 4 failed attempts. You must unlock it.", "error")
                            return redirect(url_for('auth.unlock_account'))
                        else:
                            user_ref.update({'failed_attempts': attempts})
                            flash(f"Incorrect password. You have {4 - attempts} attempts remaining.", "error")
                else:
                    flash("Incorrect Email, Registration Number, or Password.", "error")
            except Exception as e:
                print(f"Login Error: {e}")
                flash("System error during login. Please try again.", "error")
                
        else:
            flash("Please provide your Email, Registration Number, and Password.", "error")
        
    return render_template('login.html')

@auth_bp.route('/unlock', methods=['GET', 'POST'])
def unlock_account():
    """Route to unlock an account locked by brute-force protection."""
    if request.method == 'POST':
        reg_number = request.form.get('reg_number')
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        
        if not reg_number or not old_password or not new_password:
            flash("Please fill in all fields.", "error")
            return redirect(url_for('auth.unlock_account'))
            
        safe_reg_number = reg_number.strip().upper().replace('/', '_')
        user_ref = db.reference(f'profiles/{safe_reg_number}')
        user = user_ref.get()
        
        if user and user.get('is_locked'):
            # Verify they know their original password
            if check_password_hash(user.get('password', ''), old_password):
                if len(new_password) < 6:
                    flash("New password must be at least 6 characters.", "error")
                else:
                    # Unlock and update password
                    user_ref.update({
                        'password': generate_password_hash(new_password),
                        'is_locked': False,
                        'failed_attempts': 0
                    })
                    flash("Account unlocked successfully! You can now log in.", "success")
                    return redirect(url_for('auth.login'))
            else:
                flash("Initial password incorrect. Cannot unlock.", "error")
        else:
            flash("Account not found or is not currently locked.", "error")
            
    return render_template('unlock.html')

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Handles password reset requests via email OTP."""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        # Find user by email
        users = db.reference('profiles').order_by_child('email').equal_to(email).get()
        if users:
            user_id = list(users.keys())[0]
            
            # Generate OTP
            otp_code = str(random.randint(100000, 999999))
            db.reference(f'profiles/{user_id}').update({'reset_code': otp_code})
            
            # Send Email
            send_verification_email(email, "Student", otp_code)
            
            session['reset_user_id'] = user_id
            flash("A password reset code has been sent to your email.", "success")
            return redirect(url_for('auth.reset_password'))
        else:
            flash("No account found with that email address.", "error")
            
    return render_template('forgot_password.html')

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    """Verifies the reset OTP and applies the new password."""
    user_id = session.get('reset_user_id')
    if not user_id:
        return redirect(url_for('auth.forgot_password'))
        
    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        new_password = request.form.get('new_password')
        
        user_ref = db.reference(f'profiles/{user_id}')
        user = user_ref.get()
        
        if user and str(user.get('reset_code')) == otp_code:
            if len(new_password) < 6:
                flash("Password must be at least 6 characters.", "error")
                return redirect(url_for('auth.reset_password'))
                
            user_ref.update({
                'password': generate_password_hash(new_password),
                'reset_code': None,
                'is_locked': False,  # Automatically unlocks them if they were locked
                'failed_attempts': 0
            })
            session.pop('reset_user_id', None)
            flash("Password reset successfully! Please log in with your new password.", "success")
            return redirect(url_for('auth.login'))
        else:
            flash("Invalid reset code.", "error")
            
    return render_template('reset_password.html')

@auth_bp.route('/delete_account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    user_id = session['user_id']
    success = delete_user_account(user_id)

    if success:
        session.clear()
        flash("Your account and all associated data have been permanently deleted.", "success")
        return redirect(url_for('home'))
    else:
        flash("Error deleting account. Please try again later.", "error")
        return redirect(url_for('settings'))


# ==========================================
# FIXED B2B REGISTRATION ROUTE
# ==========================================
@auth_bp.route('/business/register', methods=['GET', 'POST'])
def business_register():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        business_name = request.form.get('business_name', '')

        try:
            # Check if email exists
            all_restaurants = db.reference('restaurants').get() or {}
            for r_data in all_restaurants.values():
                if isinstance(r_data, dict) and r_data.get('email') == email:
                    flash('This email is already registered. Please log in.', 'warning')
                    return redirect(url_for('business_login'))

            # Generate secure IDs and Hashes
            restaurant_id = str(uuid.uuid4())
            hashed_password = generate_password_hash(password)
            
            # Create the data payload bypassing the old register_restaurant logic
            new_merchant = {
                'business_name': business_name,
                'location': request.form.get('location'),
                'owner_name': request.form.get('owner_name'),
                'phone': request.form.get('phone'),
                'email': email,  
                'password': hashed_password,  # Hashed securely
                'conditions': request.form.get('conditions'),
                'subscription_active': False,
                'profile_views': 0,
                'qr_scans': 0,
                'hourly_stats': {}
            }

            # Save directly to Firebase
            db.reference(f'restaurants/{restaurant_id}').set(new_merchant)
            
            # UNIFIED AUTO-LOGIN
            session['user_id'] = restaurant_id
            session['user_name'] = business_name
            session['role'] = 'business'
            
            flash('Merchant account created successfully! Welcome to your dashboard.', 'success')
            return redirect(url_for('business_dashboard')) # Redirects perfectly to main.py
            
        except Exception as e:
            print(f"Registration Error: {e}") 
            flash('Failed to create account. Please check your connection and try again.', 'error')
            return redirect(url_for('auth.business_register'))

    return render_template('restaurant_signup.html')


@auth_bp.route('/resend_otp', methods=['POST'])
def resend_otp():
    """Generates a new OTP and updates Firebase safely."""
    # Grab the IDs from the session
    user_id = session.get('temp_user_id')
    email = session.get('temp_user_email') 
    
    if not user_id or not email:
        flash("Session expired. Please log in or sign up again.", "error")
        return redirect(url_for('auth.login'))

    # Generate a new 6-digit OTP
    new_otp = str(random.randint(100000, 999999))
    
    try:
        # BUG FIX: Write the new code directly to the actual user's profile
        db.reference(f'profiles/{user_id}').update({'verification_code': new_otp})
        
        # Fire your email sending function here!
        # (Pass 'Student' as name fallback since we don't fetch it here)
        send_verification_email(email, "Student", new_otp)
        
        print(f"📧 NEW OTP SENT TO {email}: {new_otp}")
        flash("A new 6-digit code has been sent to your email.", "success")
        
    except Exception as e:
        print(f"Error resending OTP: {e}")
        flash("Failed to resend code. Please try again.", "error")
        
    return redirect(url_for('auth.verify_email'))


@auth_bp.route('/logout')
def logout():
    session.clear() 
    flash("You have been logged out.", "success")
    return redirect(url_for('home'))