import os
import sys
import time
import random
import io
import base64
import qrcode
import json
import logging
import requests
import threading
from functools import wraps
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import ipaddress
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from pywebpush import webpush, WebPushException
from groq import Groq
from flask_wtf.csrf import CSRFProtect
# ==========================================
# 1. PATH SETUP & ENVIRONMENT
# ==========================================
load_dotenv()
#  This line tells Python where to find the 'app' folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Define East Africa Time (UTC+3) for accurate Kenyan timestamps
EAT = timezone(timedelta(hours=3))

# Configure Central Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 2. LOCAL APP IMPORTS
# ==========================================
#  NOW it is safe to import from 'app' because the path is set up above! 👇
from app.email_service import (
    send_date_approval_email, 
    send_date_request_to_merchant_email,
    send_verification_email
)

from app.database import (
    db, get_all_profiles, save_schedule, update_user_bio, 
    save_chat_message, get_chat_history, save_swipe, save_date_feedback,
    get_restaurant, get_restaurant_bookings, update_booking_status, terminate_connection,
    get_all_restaurants, delete_user_account, increment_restaurant_view,
    get_user_matches, create_date_booking
)

from app.services.recommendation_engine import generate_ranked_deck
from app.services.moderation import contains_phone_number, analyze_safety
from app.payments import initiate_stk_push

# ==========================================
# 3. AI COMPANION SERVICE (GROQ)
# ==========================================
# Pull the key securely from the system environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def get_ai_companion_response(user_text, user_gender="unknown"):
    """Connects to Groq and dynamically adjusts persona based on user gender."""
    if not client:
        print("⚠️ GROQ_API_KEY is missing from api_key.py!")
        return "My AI brain is currently resting. (API Key missing!)"

    model_id = "llama-3.1-8b-instant" 
    
    # Determine the AI's persona based on the user's gender
    user_g = str(user_gender).strip().lower()
    
    if user_g in ["male", "m"]:
        ai_persona = "female"
        target_user = "male"
    elif user_g in ["female", "f"]:
        ai_persona = "male"
        target_user = "female"
    else:
        # Fallback if gender isn't set properly
        ai_persona = "friendly"
        target_user = "university"

    # Build the dynamic system prompt
    system_prompt = (
        f"You are a friendly, flirty, and supportive {ai_persona} AI dating companion "
        f"chatting with a {target_user} university student at Masinde Muliro University of Science and Technology (MMUST). "
        "Keep your responses short, clean, and encouraging. Occasionally use Kenyan campus slang."
    )
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]
    
    try:
        chat_completion = client.chat.completions.create(
            messages=messages,
            model=model_id,
            max_tokens=150,
            temperature=0.7,
            top_p=0.9
        )
        
        reply = chat_completion.choices[0].message.content.strip()
        return reply if reply else "I'm listening, tell me more!"
        
    except Exception as e:
        print(f"⚠️ Groq API Error: {e}")
        return "The campus Wi-Fi is acting up! Try sending that again?"
# ==========================================
# 4. INITIALIZE FLASK APP & WEBSOCKETS
# ==========================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "delstarford_works_secret_2026")

# --- NEW: FIREWALL & RATE LIMITER ---
# This tracks user IPs and blocks them if they spam requests
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["500 per day", "100 per hour"],
    storage_uri="memory://" # Stores tracking data in server memory
)
# Initialize CSRF Protection
csrf = CSRFProtect(app)
# Known Safaricom API IP Subnets
SAFARICOM_IPS = [
    "196.201.214.0/24",
    "196.201.213.0/24",
    "196.201.212.0/24",
    "196.201.211.0/24"
]

def get_real_ip():
    """Safely extracts the real IP behind cloud proxies like Render or Nginx."""
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr
# app/main.py

# ==========================================
# 🛡️ SESSION HARDENING CONFIG
# ==========================================
app.config.update(
    # Prevents JavaScript from reading the cookie (prevents XSS hijacking)
    SESSION_COOKIE_HTTPONLY=True,
    
    # Ensures the cookie is only sent over HTTPS (Prevents Wi-Fi sniffing)
    # Note: If you are running locally (http://127.0.0.1:5000), 
    # set this to False, but ALWAYS True for your live site.
    SESSION_COOKIE_SECURE=True, 
    
    # Prevents CSRF (already handled by Flask-WTF, but this is an extra layer)
    SESSION_COOKIE_SAMESITE='Lax',
    
    # Hardens the session length to 7 days
    PERMANENT_SESSION_LIFETIME=timedelta(days=7)
)
def is_safaricom_ip(ip_str):
    """Verifies if an incoming request is actually from Safaricom."""
    try:
        ip = ipaddress.ip_address(ip_str)
        for network in SAFARICOM_IPS:
            if ip in ipaddress.ip_network(network):
                return True
        # Allow local testing via Postman/ngrok ONLY if running in debug mode
        if app.debug and ip_str == '127.0.0.1': 
            return True 
        return False
    except ValueError:
        return False
# VAPID Keys for Push Notifications
# Using os.getenv so your personal email isn't hardcoded if you share the code
mail_username = os.getenv("MAIL_USERNAME", "delstarfordisaiah@gmail.com")
app.config['VAPID_PRIVATE_KEY'] = "private_key.pem" 
app.config['VAPID_CLAIMS'] = {"sub": f"mailto:{mail_username}"}
import os

# Secure in production, False in development
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Register Blueprints
from app.routes.auth import auth_bp
app.register_blueprint(auth_bp)


# ==========================================
# 5. SECURITY DECORATORS & HELPERS
# ==========================================
def login_required(f):
    """Decorator: Ensures a user is logged in before accessing a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in or sign up to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def requires_subscription(f):
    """Decorator: Checks if a logged-in student has paid the subscription."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
            
        user_id = session.get('user_id')
        user_data = db.reference(f'profiles/{user_id}').get()
        
        if not user_data or not user_data.get('is_paid', False):
            flash("Subscription Required: Please pay 20 KSH to access this feature.", "warning")
            return render_template('paywall.html') 
            
        return f(*args, **kwargs)
    return decorated_function

def trigger_match_notification(target_user_id, current_user_name):
    """Sends a Web Push Notification to the target user when a match occurs."""
    sub_ref = db.reference(f'push_subscriptions/{target_user_id}').get()
    
    if not sub_ref:
        print(f" User {target_user_id} has not enabled push notifications.")
        return

    payload = json.dumps({
        "title": "It's a Match! 🔥",
        "body": f"You and {current_user_name} liked each other. Tap to say hi!",
        "url": "/matches"
    })

    try:
        webpush(
            subscription_info=sub_ref,
            data=payload,
            vapid_private_key=app.config['VAPID_PRIVATE_KEY'],
            vapid_claims=app.config['VAPID_CLAIMS']
        )
        print(f" Push notification instantly sent to {target_user_id}!")
    except WebPushException as ex:
        print(f" Push failed: {repr(ex)}")
        if ex.response and ex.response.status_code == 410:
            db.reference(f'push_subscriptions/{target_user_id}').delete()
            print(f"🧹 Cleaned up expired push token for {target_user_id}")

# ==========================================
# 6. WEBSOCKET EVENTS (CHAT & AI MODERATION)
# ==========================================
from datetime import datetime

@socketio.on('connect')
def handle_connect():
    """Security Step: Automatically join a private room based on user_id."""
    user_id = session.get('user_id')
    if user_id:
        join_room(user_id)

@socketio.on('typing')
def handle_typing(data):
    """Routes the typing indicator securely."""
    receiver_id = data.get('receiver_id')
    sender_id = session.get('user_id')
    
    if receiver_id and sender_id:
        # Force the sender ID so clients cannot spoof who is typing
        data['sender'] = sender_id
        emit('user_typing', data, to=receiver_id)

@socketio.on('send_message')
def handle_message(data):
    # 1. SECURITY: Ensure user is authenticated
    sender_id = session.get('user_id')
    if not sender_id:
        return

    receiver_id = data.get('receiver_id')
    msg_text = data.get('text', '').strip()
    msg_type = data.get('type', 'text')

    # Prevent empty "ghost" messages
    if not receiver_id or not msg_text:
        return

    # 2. SERVER-SIDE STAMPING: Overwrite payload to prevent client spoofing
    data['sender'] = sender_id
    data['timestamp'] = datetime.now().isoformat()

    # ==========================================
    # ROUTE A: AI COMPANION LOGIC
    # ==========================================
    if receiver_id == 'AI_COMPANION':
        # Echo to all of the user's active devices (phone, laptop, etc.)
        emit('receive_message', data, to=sender_id)
        emit('user_typing', {'sender': 'AI_COMPANION', 'is_typing': True}, to=sender_id)
        
        # Safely fetch gender
        current_user_gender = "unknown"
        try:
            user_profile = db.reference(f'profiles/{sender_id}').get()
            if user_profile and 'gender' in user_profile:
                current_user_gender = user_profile['gender']
        except Exception:
            pass
        
        # Async worker for AI generation
        def ai_worker(query, user_room, gender):
            try:
                ai_reply = get_ai_companion_response(query, user_gender=gender)
                socketio.emit('user_typing', {'sender': 'AI_COMPANION', 'is_typing': False}, to=user_room)
                socketio.emit('receive_message', {
                    'sender': 'AI_COMPANION',
                    'type': 'text',
                    'text': ai_reply,
                    'timestamp': datetime.now().isoformat()
                }, to=user_room)
            except Exception as e:
                print(f"AI Worker Error: {e}")

        # Use SocketIO's safe background task manager instead of standard threading
        socketio.start_background_task(ai_worker, msg_text, sender_id, current_user_gender)
        return

    # ==========================================
    # ROUTE B: HUMAN-TO-HUMAN SAFETY MODERATION
    # ==========================================
    if msg_type == 'text':
        try:
            safety_check = analyze_safety(msg_text)
            
            if not safety_check.get('is_safe', True):
                if safety_check.get('flag') in ['self_harm', 'violence']:
                    # Offload DB write to prevent blocking the socket
                    def save_alert():
                        db.reference('admin_alerts').push({
                            'sender': sender_id,
                            'receiver': receiver_id,
                            'message': msg_text,
                            'flag': safety_check['flag'],
                            'timestamp': datetime.now().isoformat()
                        })
                    socketio.start_background_task(save_alert)
                
                # Warn the sender privately across all their devices
                warning_msg = {'sender': 'SYSTEM_AI', 'type': 'text', 'text': safety_check.get('system_reply', 'Message flagged.')}
                emit('receive_message', warning_msg, to=sender_id) 
                return

            if contains_phone_number(msg_text):
                warning_msg = {
                    'sender': 'SYSTEM_AI',
                    'type': 'text',
                    'text': "SYSTEM ALERT: Sharing phone numbers is restricted for your safety."
                }
                emit('receive_message', warning_msg, to=sender_id) 
                return
        except Exception as e:
            print(f"Safety Check Error: {e}")

    # ==========================================
    # ROUTE C: LIGHTNING FAST MESSAGE DELIVERY
    # ==========================================
    
    # 1. Deliver instantly to UI (Zero-latency feel)
    emit('receive_message', data, to=receiver_id)
    emit('receive_message', data, to=sender_id)
    
    # 2. Save to database in the background
    def background_db_save():
        try:
            save_chat_message(sender_id, receiver_id, msg_text, msg_type)
        except Exception as e:
            print(f"DB Save Error: {e}")

    socketio.start_background_task(background_db_save)
    
    
# Note: Your Flask routes (@app.route) would continue below this if they are in main.py          
# ==========================================
# CORE B2C PAGES (STUDENTS)
# ==========================================

@app.route('/')
def home():
    # Public route
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/safety')
def safety():
    # Public route
    return render_template('safety.html', current_user=session.get('user_name'))

@app.route('/privacy')
def privacy():
    # Public route
    return render_template('privacy.html', current_user=session.get('user_name'))

@app.route('/terms')
def terms():
    # Public route
    return render_template('terms.html', current_user=session.get('user_name'))

@app.route('/venues')
def venues():
    # Public route
    active_venues = get_all_restaurants(active_only=True)
    return render_template('venues.html', current_user=session.get('user_name'), venues=active_venues)

from flask import render_template, session, redirect, url_for, flash
from flask import session, flash, redirect, url_for, render_template
# Make sure your db is imported! e.g., from app.database import db

import random


@app.route('/swipe')
@requires_subscription
def swipe():
    """
    Renders the main Tinder-style discovery deck.
    Requires the user to be authenticated and have an active premium subscription.
    """
    user_id = session.get('user_id')
    
    # 1. Fallback Validation (Safety Net)
    if not user_id:
        flash("Your session expired. Please log in again.", "warning")
        return redirect(url_for('auth.login')) 

    # 2. Fetch Current User Data & Swipes
    user_profile = db.reference(f'profiles/{user_id}').get() or {}
    user_swipes = db.reference(f'swipes/{user_id}').get() or {}

    # Extract Current User's Gender for strict filtering
    current_user_gender = user_profile.get('gender', '').strip().lower()

    # --- THE ALGORITHM DATA FETCH ---
    # Fetch people who have a pending Secret Crush on THIS user
    crushes_on_me = db.reference(f'secret_crushes/{user_id}').get() or {}
    pending_crushers = [sender_id for sender_id, data in crushes_on_me.items() if data.get('status') == 'pending']

    # Fetch User Preferences
    user_settings = user_profile.get('settings', {})
    gender_pref = user_settings.get('looking_for', 'Everyone')
    my_intent = user_profile.get('intent', 'none')
    
    # Prepare for Bio matching
    my_bio_words = set(user_profile.get('bio', '').lower().replace('.', '').replace(',', '').split())
    stop_words = {'i', 'am', 'a', 'the', 'and', 'to', 'for', 'in', 'of', 'my', 'is', 'at', 'on', 'with', 'student', 'mmust'}
    my_keywords = my_bio_words - stop_words

    # 3. Bundle Context for the Frontend
    current_user = {
        'id': user_id,
        'name': user_profile.get('name', session.get('user_name', 'Student')).split(' ')[0], 
        'img': user_profile.get('img') or url_for('static', filename='img/placeholder.png'),
        'settings': user_settings
    }

    # 4. Build the Discovery Deck
    potential_matches = []
    all_profiles = get_all_profiles() # Fetch everyone
    
    for p in all_profiles:
        p_id = p.get('id')
        p_gender = p.get('gender', '').strip().lower()
        
        # --- STRICT OPPOSITE-GENDER RULE ---
        # If both users have a gender set and they are the same, completely skip this profile
        if current_user_gender and p_gender and current_user_gender == p_gender:
            continue
        
        # SKIP CONDITIONS:
        # - Don't show the user themselves
        # - Don't show profiles that are hidden
        # - Don't show people the user has already swiped on (liked/passed)
        if p_id == user_id or not p.get('is_visible', True) or p_id in user_swipes:
            continue
            
        # GENDER PREFERENCE FILTER (If they specifically selected Male or Female)
        if gender_pref != 'Everyone':
            if p_gender != gender_pref.lower():
                continue
                
        # --- THE SCORING ALGORITHM ---
        base_score = p.get('ai_score', random.randint(65, 80))
        bonus = 0
        
        # Intent Bonus
        p_intent = p.get('intent', 'none')
        if my_intent != 'none' and p_intent == my_intent:
            bonus += 10
            
        # Bio Overlap Bonus
        p_bio_words = set(p.get('bio', '').lower().replace('.', '').replace(',', '').split())
        if len((p_bio_words - stop_words) & my_keywords) > 0:
            bonus += 5
            
        final_score = min(base_score + bonus, 99)
        
        # SECRET CRUSH OVERRIDE (Forces them to the absolute front of the line)
        if p_id in pending_crushers:
            final_score = 100 
        
        potential_matches.append({
            'id': p_id,
            'name': p.get('name', 'Student').split(' ')[0],
            'age': p.get('age', 18),
            'major': p.get('major', 'MMUST Student'),
            'bio': p.get('bio', 'Hey! I am using MMUST Dating AI.'),
            'img': p.get('img') or url_for('static', filename='img/placeholder.png'),
            'intent': p_intent, # Passes the intent so the frontend tag works!
            'compatibility': final_score,
            'is_perfect_match': final_score >= 80  # Flag for the frontend badge
        })

    # 5. Sort the deck: Show the Highest Compatibility matches first!
    potential_matches.sort(key=lambda x: x['compatibility'], reverse=True)

    return render_template(
        'swipe.html', 
        current_user=current_user,
        potential_matches=potential_matches
    )

@app.route('/notifications')
@requires_subscription # Or @login_required depending on your setup
def setup_notifications():
    """Renders the dedicated Push Notification onboarding page."""
    return render_template('notifications.html', current_user=session.get('user_name', 'Student').split(' ')[0])

import random
@app.route('/dashboard')
@requires_subscription
def dashboard():
    """THE MAIN STUDENT COMMAND CENTER (OPEN DIRECTORY MODE)"""
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
    # --- Extract the subscription expiry date for the countdown timer ---
    subscription_expiry = user_data.get('subscription_expiry', '')
    
    # Extract Current User's Gender for matching logic
    current_user_gender = user_data.get('gender', '').strip().lower()
    
    my_matches = []
    
    # 1. BLAZING FAST FETCH: Grab all profiles in one single network call
    all_profiles_dict = db.reference('profiles').get() or {}
    
    if ai_mode:
        my_matches.append({
            'id': 'AI_COMPANION',
            'name': 'AI Wingman 🤖',
            'bio': 'Your personal AI wingman. Ready to chat!',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=wingman&backgroundColor=e60026',
            'compatibility': 100,
            'is_perfect_match': True
        })
    else:
        for p_id, p in all_profiles_dict.items():
            if not isinstance(p, dict):
                continue
                
            partner_gender = p.get('gender', '').strip().lower()

            # Skip the user themselves, hidden profiles, and non-premium users
            if p_id != user_id and p.get('is_visible', True) and p.get('is_paid') == True:
                # Fetch or simulate compatibility score
                ai_score = p.get('ai_score', random.randint(65, 95))
                
                # --- NEW LOGIC: Everyone is visible, but only opposite genders can be a "Perfect Match" ---
                is_opposite_gender = bool(current_user_gender and partner_gender and current_user_gender != partner_gender)
                
                is_perfect_match = False
                if is_opposite_gender and ai_score >= 80:
                    is_perfect_match = True
                
                my_matches.append({
                    'id': p_id,
                    'name': p.get('name', 'Student').split(' ')[0], 
                    'bio': p.get('bio', 'MMUST Student'),
                    'img': p.get('img') or url_for('static', filename='img/placeholder.png'),
                    'compatibility': ai_score,
                    'is_perfect_match': is_perfect_match # Only True for opposite gender with high score
                })
        
        # 2. Sort by highest compatibility first, pushing Perfect Matches to the top
        my_matches.sort(key=lambda x: x['compatibility'], reverse=True)

        # 3. Always pin the AI Wingman to the front of the line
        my_matches.insert(0, {
            'id': 'AI_COMPANION',
            'name': 'AI Wingman 🤖',
            'bio': 'Need dating advice or an icebreaker? I am here to help!',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=wingman&backgroundColor=e60026',
            'compatibility': 100,
            'is_perfect_match': True
        })

    # 4. FETCH DATE BOOKINGS (Single network call)
    all_bookings = db.reference('bookings').get() or {}
    all_restaurants = db.reference('restaurants').get() or {}
    
    pending_dates_count = 0
    upcoming_dates = []

    for b_id, b_data in all_bookings.items():
        if not isinstance(b_data, dict): 
            continue
        
        if b_data.get('user_a_id') == user_id or b_data.get('user_b_id') == user_id:
            status = b_data.get('status')
            
            if status == 'Pending':
                pending_dates_count += 1
            elif status == 'Approved':
                partner_id = b_data.get('user_b_id') if b_data.get('user_a_id') == user_id else b_data.get('user_a_id')
                partner_profile = all_profiles_dict.get(partner_id, {})
                
                venue_id = b_data.get('venue_id')
                venue_data = all_restaurants.get(venue_id, {})
                
                upcoming_dates.append({
                    'partner_name': partner_profile.get('name', 'Your Date').split(' ')[0],
                    'partner_img': partner_profile.get('img') or '/static/img/placeholder.png',
                    'restaurant_name': venue_data.get('business_name', 'Unknown Venue'),
                    'location': venue_data.get('location', 'Kakamega CBD'),
                    'day': b_data.get('day', 'TBD'),
                    'time': b_data.get('time', 'TBD'),
                    'perk': venue_data.get('conditions', '')
                })

    return render_template(
        'dashboard.html', 
        current_user=session.get('user_name', 'Student').split(' ')[0], 
        matches=my_matches,
        pending_dates_count=pending_dates_count,
        upcoming_dates=upcoming_dates,
        subscription_expiry=subscription_expiry
    )
    
@app.route('/api/unmatch', methods=['POST'])
@login_required
def unmatch_user():
    data = request.json
    user_id = session.get('user_id')
    target_id = data.get('target_id')
    reason = data.get('reason') # Optional report reason

    if not target_id:
        return jsonify({"status": "error", "message": "Missing target user"}), 400

    try:
        # 1. Generate the unique match ID
        match_id = "_".join(sorted([user_id, target_id]))
        
        # 2. Delete the mutual match
        db.reference(f'matches/{match_id}').delete()

        # 3. Delete the chat history (Optional, but good for privacy)
        db.reference(f'chats/{match_id}').delete()

        # 4. Overwrite their previous swipes so they don't show up in the deck again
        timestamp = datetime.now(EAT).isoformat()
        db.reference(f'swipes/{user_id}/{target_id}').set({'action': 'unmatched', 'timestamp': timestamp})
        db.reference(f'swipes/{target_id}/{user_id}').set({'action': 'unmatched', 'timestamp': timestamp})

        # 5. If they provided a reason, log it to the Admin Reports node
        if reason:
            db.reference('reports').push({
                'reporter_id': user_id,
                'reported_id': target_id,
                'reason': reason,
                'timestamp': timestamp,
                'status': 'pending_review'
            })

        return jsonify({"status": "success"})
        
    except Exception as e:
        logger.error(f"Unmatch Error: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    
    
    
import hashlib
import os

def hash_reg_number(reg_num):
    """
    Standardizes the reg number (removes spaces, makes uppercase)
    and returns an unbreakable SHA-256 hash.
    """
    if not reg_num: return None
    clean_reg = str(reg_num).strip().upper()
    # Add a "salt" (a secret key) to make it mathematically impossible to crack
    secret_salt = os.getenv("HASH_SALT", "MMUST_DATING_SECURE_2026")
    salted_reg = f"{clean_reg}_{secret_salt}"
    
    return hashlib.sha256(salted_reg.encode('utf-8')).hexdigest()

@app.route('/api/add-crush', methods=['POST'])   
@login_required
def add_crush():
    """Secure Cryptographic Secret Crush Radar"""
    data = request.json
    user_id = session.get('user_id')
    
    # Normalize the Reg Number (strip spaces and make uppercase)
    raw_crush_id = data.get('crush_id', '').strip().upper() 

    if not raw_crush_id:
        return jsonify({"status": "error", "message": "Please enter a valid Registration Number."}), 400

    # Stop users from crushing on themselves!
    if raw_crush_id == user_id:
        return jsonify({"status": "error", "message": "You can't crush on yourself!"}), 400

    try:
        timestamp = datetime.now(EAT).isoformat()
        
        # 🛡️ THE TRUST FORTRESS: Hash the IDs immediately. 
        # We never store who likes who in plain text unless it's a mutual match.
        my_hashed_id = hash_reg_number(user_id)
        hashed_target = hash_reg_number(raw_crush_id)

        crushes_ref = db.reference('crushes')

        # 1. Save the secret crush as a Hash
        # Structure: crushes/MY_HASH/THEIR_HASH = timestamp
        crushes_ref.child(my_hashed_id).update({
            hashed_target: timestamp
        })

        # 2. Check if it is a Mutual Crush! 
        # Did the person I just hashed ALSO hash my ID and save it previously?
        target_crushes = crushes_ref.child(hashed_target).get() or {}

        if target_crushes.get(my_hashed_id):
            # 💘 IT'S A MATCH! The secret is out. 
            # We can now use the raw IDs to create the chat room.
            match_id = "_".join(sorted([user_id, raw_crush_id]))
            
            db.reference(f'matches/{match_id}').set({
                'users': {user_id: True, raw_crush_id: True},
                'matched_at': timestamp,
                'last_message': '💘 Secret Crush Radar Match! You both liked each other.',
                'last_message_time': timestamp
            })

            # Force mutual right-swipes in the database so they never see each other in the deck again
            db.reference(f'swipes/{user_id}/{raw_crush_id}').set({'action': 'like', 'timestamp': timestamp})
            db.reference(f'swipes/{raw_crush_id}/{user_id}').set({'action': 'like', 'timestamp': timestamp})

            # Trigger real-time push notifications if they are online
            def emit_crush_notifications():
                try:
                    socketio.emit('receive_message', {
                        'sender': 'SYSTEM_AI',
                        'text': '💘 OMG! Your Secret Crush just matched with you!',
                        'timestamp': timestamp
                    }, to=user_id)
                    
                    socketio.emit('receive_message', {
                        'sender': 'SYSTEM_AI',
                        'text': '💘 OMG! Your Secret Crush just matched with you!',
                        'timestamp': timestamp
                    }, to=raw_crush_id)
                except Exception as sock_err:
                    logger.warning(f"Crush socket emit failed: {sock_err}")

            socketio.start_background_task(emit_crush_notifications)

            return jsonify({
                "status": "success", 
                "match": True, 
                "message": "💘 OMG! It's a match! They liked you too. Check your messages!"
            })

        # 3. Not a mutual crush yet. Keep it encrypted and hidden.
        return jsonify({
            "status": "success", 
            "match": False, 
            "message": "🤫 Crush locked securely! If they enter your Reg Number, you'll match instantly."
        })

    except Exception as e:
        logger.error(f"Crush Radar Cryptographic Error: {e}")
        return jsonify({"status": "error", "message": "Server error while saving crush securely."}), 500
    
    
@app.route('/api/check-pending-date')
@login_required
def check_pending_date():
    user_id = request.args.get('user_id')
    # Query your bookings table for any 'Approved' dates for this user
    bookings = db.reference('bookings').order_by_child('user_a_id').equal_to(user_id).get() or {}
    
    # Check both sides (User A and User B)
    pending_found = False
    for b in bookings.values():
        if b.get('status') == 'Approved':
            pending_found = True
            break
            
    return jsonify({'has_pending': pending_found})
 
@app.route('/matches')
@app.route('/matches/<partner_id>')
@requires_subscription
def matches(partner_id=None):
    # PROTECTED: Must be logged in AND paid
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    
    # Check if the user is in "Ghost Mode" (only talking to AI)
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
    my_matches = []
    
    if ai_mode:
        # --- AI COMPANION MODE (Ghost Mode) ---
        my_matches.append({
            'id': 'AI_COMPANION', 'name': 'AI Companion',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=MMUST&backgroundColor=ffccd5', 
            'is_perfect_match': True, 'is_online': True, 'is_mutual_match': True,
            'last_message': 'Ready to chat!', 'last_message_time': 'Just now'
        })
        partner_id = 'AI_COMPANION'
    else:
        # --- HUMAN OPEN-DM MODE (Shows everyone, highlights matches) ---
        
        # 1. Get current user's gender for filtering
        current_user_gender = user_data.get('gender', '').strip().lower()

        # 2. Fetch all matches and filter in Python to PREVENT Firebase crashes!
        all_matches = db.reference('matches').get() or {}
        
        matched_data = {}
        for match_id, m_data in all_matches.items():
            if user_id in m_data.get('users', {}):
                users_dict = m_data.get('users', {})
                other_id = next((uid for uid in users_dict.keys() if uid != user_id), None)
                
                if other_id:
                    matched_data[other_id] = {
                        'last_message': m_data.get('last_message', 'You matched! Say hi.'),
                        'last_message_time': m_data.get('last_message_time', '')
                    }

        # 3. Fetch ALL profiles in the system
        all_profiles = get_all_profiles()
        
        # 4. Build the inbox list with EVERYONE
        for p in all_profiles:
            # Skip the current user themselves, hidden profiles, and unpaid profiles
            if p['id'] != user_id and p.get('is_visible', True) and p.get('is_paid') == True: 
                p_id = p['id']
                partner_gender = p.get('gender', '').strip().lower()
                is_mutual = p_id in matched_data
                
                if is_mutual:
                    last_msg = matched_data[p_id]['last_message']
                    last_msg_time = matched_data[p_id]['last_message_time']
                else:
                    last_msg = 'Tap to start chatting'
                    last_msg_time = ''
                
                # Retrieve AI score safely, default to 0
                ai_score = p.get('ai_score', 0)
                
                # Double-check opposite gender before awarding the Perfect Match badge
                is_opposite_gender = bool(current_user_gender and partner_gender and current_user_gender != partner_gender)
                is_perfect_match = is_opposite_gender and ai_score > 80
                
                my_matches.append({
                    'id': p_id,
                    'name': p.get('name', 'Student').split(' ')[0], # First Name only
                    'img': p.get('img', '/static/img/placeholder.png'),
                    'is_perfect_match': is_perfect_match, # ❤️ TRIGGERS PERFECT MATCH BADGE
                    'is_online': p.get('is_online', False),
                    'is_mutual_match': is_mutual,      # 🔥 TRIGGERS MUTUAL MATCH GLOW
                    'last_message': last_msg,
                    'last_message_time': last_msg_time
                })
        
        # 5. ALWAYS append the AI Wingman to the list
        my_matches.append({
            'id': 'AI_COMPANION', 'name': 'AI Wingman',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=wingman',
            'is_perfect_match': False, 'is_online': True, 'is_mutual_match': False,
            'last_message': 'Need dating advice?', 'last_message_time': ''
        })

        # 6. Sort matches (Mutual matches first, then by time)
        my_matches.sort(key=lambda x: (x['is_mutual_match'], x.get('last_message_time', '')), reverse=True)

        if not partner_id and my_matches:
            partner_id = my_matches[0]['id']

    # Find the data for the person currently being chatted with
    active_partner = next((m for m in my_matches if str(m['id']) == str(partner_id)), None)
    
    if partner_id and not active_partner and not ai_mode:
        flash("This student could not be found or is not available.", "warning")
        return redirect(url_for('matches'))

    # Load the chat history AS A DICTIONARY
    history = {}
    if active_partner and partner_id != 'AI_COMPANION':
        match_id = f"match_{min(user_id, partner_id)}_{max(user_id, partner_id)}"
        history = db.reference(f'matches/{match_id}/messages').get() or {}
    
    # ==========================================
    # 🧮 THE "BLURRED LINES" (BLIND DATE) MATH
    # ==========================================
    is_blind_date = False
    current_blur = 0
    messages_left = 0

    if active_partner and partner_id != 'AI_COMPANION':
        # Only apply blind date logic to mutual matches
        if active_partner.get('is_mutual_match'):
            
            # Check user settings (defaulting to True for the gamified experience)
            user_settings = user_data.get('settings', {})
            is_blind_date = user_settings.get('blind_date_mode', True)
            
            if is_blind_date:
                MESSAGES_TO_REVEAL = 20 # 10 texts sent by each person
                MAX_BLUR_PX = 15        # Starts heavily blurred
                message_count = len(history) # history is now a dict, so len(history) counts the keys
                
                if message_count >= MESSAGES_TO_REVEAL:
                    current_blur = 0
                    messages_left = 0
                else:
                    # Calculate proportional blur drop based on message count
                    current_blur = MAX_BLUR_PX - (MAX_BLUR_PX * (message_count / MESSAGES_TO_REVEAL))
                    messages_left = MESSAGES_TO_REVEAL - message_count

    return render_template('matches.html', 
                           current_user=session.get('user_name'),
                           my_matches=my_matches,
                           active_partner=active_partner,
                           chat_history=history, # Now correctly passes a dictionary
                           is_blind_date=is_blind_date,           # Pass flag to UI
                           current_blur=round(current_blur, 1),   # Pass pixel blur to UI
                           messages_left=messages_left)           # Pass progress to UI    
        
        
        
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # PROTECTED: Must be logged in (but unpaid users can still edit their profile)
    user_id = session.get('user_id')
    user_ref = db.reference(f'profiles/{user_id}')
    user_data = user_ref.get()

    if not user_data:
        flash("Profile not found. Please log in again.", "error")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        # 1. Grab raw form data
        new_bio = request.form.get('bio')
        new_age = request.form.get('age')
        new_religion = request.form.get('religion')
        new_avatar = request.form.get('avatar') # For the new 20 avatars feature!

        try:
            # 2. Build an update dictionary dynamically (Cleaner & Safer)
            update_data = {}
            if new_bio: update_data['bio'] = new_bio.strip()
            if new_religion: update_data['religion'] = new_religion.strip()
            if new_avatar: update_data['img'] = new_avatar.strip()
            
            # Prevent crashes by ensuring 'age' is actually a number before casting to int
            if new_age and new_age.isdigit():
                update_data['age'] = int(new_age)

            # 3. Only ping the database if there is actually something to update
            if update_data:
                user_ref.update(update_data)
            
            if new_religion:
                session['user_religion'] = new_religion

            # 4. Handle Schedule Updates (Using Python's 'zip' makes this much cleaner)
            days = request.form.getlist('day_of_week[]')
            starts = request.form.getlist('start_time[]')
            ends = request.form.getlist('end_time[]')
            
            for day, start, end in zip(days, starts, ends):
                if day and start and end:
                    save_schedule(user_id, day, start, end)
            
            flash("Profile and Free Time Schedule updated successfully!", "success")
            return redirect(url_for('profile'))
            
        except Exception as e:
            # Better error logging so you can track bugs in Render
            logger.error(f"Profile Update Error for user {user_id}: {e}")
            flash("Error updating profile. Please try again.", "error")

    return render_template('profile.html', current_user=session.get('user_name'), user=user_data)


@app.route('/student/<target_id>')
@requires_subscription
def view_student(target_id):
    # PROTECTED: Must be logged in AND paid
    all_profiles = get_all_profiles()
    student_profile = next((p for p in all_profiles if p['id'] == target_id), None)
    
    if not student_profile:
        flash("Oops! We couldn't find that student's profile.", "error")
        return redirect(url_for('dashboard'))
        
    return render_template('view_profile.html', student=student_profile)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # PROTECTED: Must be logged in (but unpaid users can still edit settings)
    user_id = session.get('user_id')
    user_ref = db.reference(f'profiles/{user_id}')

    if request.method == 'POST':
        # 1. Grab values from the HTML Form
        gender_pref = request.form.get('gender_pref')
        major_filter = request.form.get('major_filter')
        strict_mode = request.form.get('strict_mode') == 'on'
        ai_mode = request.form.get('ai_mode') == 'on'
        
        # 🔥 Grab the new Blind Date Mode toggle
        blind_date_mode = request.form.get('blind_date_mode') == 'on'
        
        # 🆕 Grab the new Intent Tag (defaults to 'none' if they didn't touch it)
        intent = request.form.get('intent', 'none') 

        try:
            # 2. Save filter settings to the 'settings' sub-node
            user_ref.child('settings').update({
                'looking_for': gender_pref,
                'major_filter': major_filter,
                'strict_schedule': strict_mode,
                'ai_companion_mode': ai_mode,
                'blind_date_mode': blind_date_mode  # 🔥 Save to Firebase
            })
            
            # 3. Update main profile attributes (visibility and the new intent tag)
            user_ref.update({
                'is_visible': not ai_mode,
                'intent': intent  # 🆕 Save the intent to the main profile
            })
            
            flash("Discovery settings updated successfully!", "success")
            
            # 4. Redirect them back to the Swipe deck to see their new matches!
            return redirect(url_for('swipe'))
            
        except Exception as e:
            logger.error(f"Settings Save Error: {e}")
            flash("Error saving settings to cloud.", "error")
            return redirect(url_for('settings'))

    # === GET REQUEST LOGIC ===
    # 1. Fetch the user's data from Firebase
    user_profile = user_ref.get() or {}
    user_settings = user_profile.get('settings', {})

    # 2. Map the Firebase keys to the variables the HTML template expects
    template_user_data = {
        'gender_pref': user_settings.get('looking_for', 'Everyone'),
        'major_filter': user_settings.get('major_filter', 'All'),
        'strict_mode': user_settings.get('strict_schedule', False),
        'ai_mode': user_settings.get('ai_companion_mode', False),
        
        # 🔥 Pass the blind date mode back to the template (Defaulting to True)
        'blind_date_mode': user_settings.get('blind_date_mode', True),
        
        # 🆕 Pass the intent back so the dropdown remembers their choice
        'intent': user_profile.get('intent', 'none') 
    }

    # 3. Render the page
    return render_template(
        'settings.html', 
        current_user=session.get('user_name'),
        user=template_user_data
    )
    
    
@app.route('/merchant-terms')
def merchant_terms():
    return render_template('merchant_terms.html')

    
# ==========================================
# 8. B2B PAGES (MERCHANTS)
# ==========================================
import uuid
from werkzeug.security import generate_password_hash, check_password_hash

@app.route('/business/register', methods=['GET', 'POST'])
def business_register():
    """HANDLES NEW MERCHANT SIGNUPS"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        business_name = request.form.get('business_name', '')

        try:
            # Check if email exists (Safe Python loop bypassing complex Firebase rules)
            all_restaurants = db.reference('restaurants').get() or {}
            for r_data in all_restaurants.values():
                if isinstance(r_data, dict) and r_data.get('email') == email:
                    flash('This email is already registered. Please log in.', 'warning')
                    return redirect(url_for('business_login'))

            # Generate secure IDs and Hashes
            restaurant_id = str(uuid.uuid4())
            hashed_password = generate_password_hash(password)
            
            # Create the data payload
            new_merchant = {
                'business_name': business_name,
                'location': request.form.get('location'),
                'owner_name': request.form.get('owner_name'),
                'phone': request.form.get('phone'),
                'email': email,  
                'password': hashed_password, 
                'conditions': request.form.get('conditions'),
                'subscription_active': False,
                'profile_views': 0,
                'qr_scans': 0,
                'hourly_stats': {}
            }

            # Save to Firebase
            db.reference(f'restaurants/{restaurant_id}').set(new_merchant)
            
            # AUTO-LOGIN
            session['user_id'] = restaurant_id
            session['user_name'] = business_name
            session['role'] = 'business'
            
            flash('Merchant account created successfully! Welcome to your dashboard.', 'success')
            return redirect(url_for('business_dashboard'))
            
        except Exception as e:
            logger.error(f"Registration Error: {e}") 
            flash('Failed to create account. Please check your connection and try again.', 'error')
            return redirect(url_for('business_register'))

    return render_template('restaurant_signup.html')


@app.route('/business-login', methods=['GET', 'POST'])
def business_login():
    """DEDICATED PORTAL FOR RESTAURANT OWNERS"""
    if session.get('user_id') and session.get('role') == 'business':
        return redirect(url_for('business_dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        try:
            all_restaurants = db.reference('restaurants').get() or {}
            matched_id = None
            matched_data = None
            
            for r_id, r_data in all_restaurants.items():
                if isinstance(r_data, dict) and r_data.get('email') == email:
                    matched_id = r_id
                    matched_data = r_data
                    break
            
            if matched_data:
                stored_password = matched_data.get('password', '')
                is_valid_password = False
                
                # HYBRID CHECK: Supports old plain-text OR new hashed passwords
                if stored_password == password:
                    is_valid_password = True  
                elif stored_password.startswith('scrypt:') or stored_password.startswith('pbkdf2:'):
                    is_valid_password = check_password_hash(stored_password, password)

                if is_valid_password:
                    session['user_id'] = matched_id
                    session['user_name'] = matched_data.get('business_name', 'Partner')
                    session['role'] = 'business'
                    
                    flash("Welcome back to your Partner Dashboard!", "success")
                    return redirect(url_for('business_dashboard'))
            
            flash("Invalid business email or password.", "error")
            
        except Exception as e:
            logger.error(f"Business Login Error: {e}")
            flash("Connection error. Please try again.", "error")

    return render_template('b2b_login.html')


@app.route('/business/dashboard')
def business_dashboard():
    """THE MERCHANT COMMAND CENTER"""
    if not session.get('user_id') or session.get('role') != 'business':
        flash("Access Denied. Please log in through the Merchant Portal.", "error")
        return redirect(url_for('business_login'))

    restaurant_id = session.get('user_id')
    
    try:
        restaurant = get_restaurant(restaurant_id) or {}
        bookings = get_restaurant_bookings(restaurant_id) or []
    except Exception as e:
        logger.error(f"Dashboard Data Fetch Error: {e}")
        restaurant, bookings = {}, []

    restaurant.setdefault('hourly_stats', {})
    restaurant.setdefault('qr_scans', 0)
    restaurant.setdefault('profile_views', 0)

    pending_count = sum(1 for b in bookings if b.get('status') == 'Pending')
    approved_count = sum(1 for b in bookings if b.get('status') == 'Approved')
    
    for b in bookings:
        try:
            user_a = db.reference(f"profiles/{b.get('user_a_id')}").get() or {}
            user_b = db.reference(f"profiles/{b.get('user_b_id')}").get() or {}
            
            b['user_a_name'] = user_a.get('name', 'Student 1').split(' ')[0] if user_a.get('name') else 'Student 1'
            b['user_b_name'] = user_b.get('name', 'Student 2').split(' ')[0] if user_b.get('name') else 'Student 2'
        except Exception as e:
            logger.warning(f"Failed to fetch student names for booking: {e}")
            b['user_a_name'] = "Student 1" 
            b['user_b_name'] = "Student 2"

    return render_template('business_dashboard.html', 
                           restaurant=restaurant, 
                           bookings=bookings,
                           pending_count=pending_count, 
                           approved_count=approved_count)
                           
@app.route('/business/booking/<booking_id>/<action>', methods=['POST'])
def manage_booking(booking_id, action):
    """ALLOWS RESTAURANTS TO ACCEPT/DECLINE RESERVATIONS AND NOTIFIES USERS"""
    if session.get('role') != 'business': 
        return redirect(url_for('home'))
        
    status = 'Approved' if action == 'approve' else 'Declined'
    
    try:
        # 1. Update the database
        update_booking_status(booking_id, status)
        
        # 2. If Approved, fetch details and send emails in the background
        if status == 'Approved':
            # Fetch the specific booking from Firebase
            booking = db.reference(f'bookings/{booking_id}').get()
            
            if booking:
                # Fetch both users' profiles
                user_a = db.reference(f"profiles/{booking.get('user_a_id')}").get() or {}
                user_b = db.reference(f"profiles/{booking.get('user_b_id')}").get() or {}
                
                # Fetch the restaurant's profile
                restaurant_id = session.get('user_id')
                restaurant = db.reference(f"restaurants/{restaurant_id}").get() or {}
                
                # Prepare the variables
                r_name = restaurant.get('business_name', 'Our Venue')
                r_location = restaurant.get('location', 'Check app for details')
                d_day = booking.get('day', 'your scheduled day')
                d_time = booking.get('time', 'your scheduled time')

                # We use threading so the Python server sends the emails in the background.
                # This prevents the Merchant Dashboard from "freezing" for 3 seconds while emails send!
                
                if user_a.get('email'):
                    user_a_name = user_a.get('name', 'Student').split(' ')[0]
                    user_b_name = user_b.get('name', 'Your Date').split(' ')[0]
                    
                    threading.Thread(target=send_date_approval_email, args=(
                        user_a['email'], user_a_name, user_b_name, r_name, d_day, d_time, r_location
                    )).start()
                    
                if user_b.get('email'):
                    user_b_name = user_b.get('name', 'Student').split(' ')[0]
                    user_a_name = user_a.get('name', 'Your Date').split(' ')[0]
                    
                    threading.Thread(target=send_date_approval_email, args=(
                        user_b['email'], user_b_name, user_a_name, r_name, d_day, d_time, r_location
                    )).start()

        flash(f"Reservation {status.lower()}! The couple has been notified via email.", "success")
        
    except Exception as e:
        logger.error(f"Error updating booking {booking_id}: {e}")
        flash("Failed to update reservation. Try again.", "error")
        
    return redirect(url_for('business_dashboard'))


@app.route('/business/qr')
def merchant_qr():
    """GENERATES THE UNIQUE QR CODE FOR THE RESTAURANT"""
    if session.get('role') != 'business': 
        return redirect(url_for('home'))
    
    restaurant_id = session.get('user_id')
    restaurant_name = session.get('user_name', 'Merchant')
    
    verify_url = f"{request.url_root.rstrip('/')}/verify_customer/{restaurant_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(verify_url)
    qr.make(fit=True)
    
    buf = io.BytesIO()
    qr.make_image(fill_color="#720000", back_color="white").save(buf)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    
    return render_template('merchant_qr.html', 
                           qr_code=image_base64, 
                           restaurant_name=restaurant_name)


@app.route('/verify_customer/<restaurant_id>')
def verify_customer(restaurant_id):
    """THE PAGE STUDENTS SEE WHEN THEY SCAN A RESTAURANT'S QR CODE"""
    if 'user_id' not in session: 
        session['next_url'] = request.url 
        flash("Please log in to verify your student discount.", "warning")
        return redirect(url_for('auth.login'))

    user_id = session.get('user_id')
    
    try:
        user_data = db.reference(f'profiles/{user_id}').get()
        restaurant = db.reference(f'restaurants/{restaurant_id}').get()
    except Exception as e:
        logger.error(f"Verification Fetch Error: {e}")
        flash("Database connection error. Please try again.", "error")
        return redirect(url_for('dashboard'))

    if not restaurant: 
        flash("Invalid QR Code. This venue is not part of our network.", "error")
        return redirect(url_for('dashboard'))

    if not user_data or not user_data.get('is_paid'):
        status = "REJECTED"
        message = "No active subscription found. Pay 20 KSH via M-Pesa to unlock exclusive campus discounts."
        color = "#E60026"
    else:
        status = "VERIFIED"
        perk = restaurant.get('conditions', 'Standard Student Discount')
        message = f"Valid Premium Student! Please apply the '{perk}' discount."
        color = "#28a745"
        
        try:
            qr_ref = db.reference(f'restaurants/{restaurant_id}/qr_scans')
            qr_ref.set((qr_ref.get() or 0) + 1)
            
            current_hour = str(datetime.now(EAT).hour)
            hour_ref = db.reference(f'restaurants/{restaurant_id}/hourly_stats/{current_hour}')
            hour_ref.set((hour_ref.get() or 0) + 1)
            
            alert_ref = db.reference(f'merchant_alerts/{restaurant_id}')
            alert_ref.set({
                'student_name': user_data.get('name', 'A Student').split(' ')[0],
                'timestamp': datetime.now(EAT).isoformat(),
                'status': 'new'
            })
        except Exception as e: 
            logger.error(f"Error updating analytics: {e}")

    return render_template('verification_result.html', 
                           status=status, 
                           message=message, 
                           color=color,
                           restaurant_name=restaurant.get('business_name', 'This Venue'))
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_date_approval_email(to_email, user_name, partner_name, restaurant_name, date_day, date_time, location):
    """Sends a professional confirmation email to a student when a date is approved."""
    
    sender_email = os.getenv("MAIL_USERNAME")
    sender_password = os.getenv("MAIL_PASSWORD") # Ensure this is an App Password if using Gmail
    
    if not sender_email or not sender_password:
        print("⚠️ Email credentials missing. Cannot send approval email.")
        return

    subject = f"💌 Your Date at {restaurant_name} is Confirmed!"
    
    # Beautiful HTML Email Template
    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; background-color: #f4f6f8; padding: 20px;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 16px; border-top: 6px solid #E60026; box-shadow: 0 4px 15px rgba(0,0,0,0.05);">
                <h2 style="color: #720000; margin-top: 0;">Great news, {user_name}! 🎉</h2>
                
                <p style="color: #333; font-size: 16px; line-height: 1.5;">
                    Your upcoming date with <strong>{partner_name}</strong> has been officially approved by the management at <strong>{restaurant_name}</strong>.
                </p>
                
                <div style="background: #FEF2F4; padding: 20px; border-radius: 12px; margin: 25px 0;">
                    <h3 style="color: #E60026; margin-top: 0; margin-bottom: 15px; font-size: 18px;">🍽️ Your Reservation Details</h3>
                    <p style="margin: 5px 0; color: #4A0008;"><strong>When:</strong> {date_day} at {date_time}</p>
                    <p style="margin: 5px 0; color: #4A0008;"><strong>Where:</strong> {restaurant_name} ({location})</p>
                </div>
                
                <p style="color: #555; font-size: 15px; line-height: 1.5;">
                    A special table has been specifically reserved for you. When you arrive, simply open your MMUST Dating App and scan the merchant's QR code at the counter to verify your student status and claim your table!
                </p>
                
                <p style="color: #888; font-size: 14px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 15px;">
                    Have fun and stay safe! <br>
                    <strong>- The MMUST Dating AI Powered Team</strong>
                </p>
            </div>
        </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = f"MMUST Dating App <{sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    try:
        # Connecting to Gmail's SMTP server (adjust if using a different provider)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"📧 Date Approval Email successfully sent to {to_email}")
    except Exception as e:
        print(f"❌ Failed to send approval email to {to_email}: {e}")
        
          
import os
import logging
from datetime import datetime, timedelta, timezone
from flask import session, request, flash, redirect, url_for, render_template, jsonify

# Setup Admin Logger
logger = logging.getLogger('god_mode')

# Define East Africa Time (UTC+3) for accurate Kenyan timestamps
EAT = timezone(timedelta(hours=3))

import os
from flask import render_template, request, session, flash, redirect, url_for, jsonify
from datetime import datetime, timedelta

import os
from datetime import datetime, timedelta
from flask import render_template, request, session, flash, redirect, url_for, jsonify

# Import your email service functions
from app.email_service import send_broadcast_email
import os
import logging
from datetime import datetime, timedelta
from flask import request, jsonify, session, flash, url_for, render_template, redirect

logger = logging.getLogger(__name__)



import os
import logging
import random
from datetime import datetime, timedelta, timezone
from flask import request, jsonify, render_template, session, redirect, url_for, flash

# Assuming these are imported from your email_utils file:
# from email_utils import send_broadcast_email, send_admin_alert_email

logger = logging.getLogger(__name__)

# Define East Africa Time (EAT)
EAT = timezone(timedelta(hours=3))
# ==========================================
# 🚨 GOD MODE: SUPER ADMIN DASHBOARD
# ==========================================
# ==========================================
# 🚨 GOD MODE: SUPER ADMIN DASHBOARD
# ==========================================
@app.route('/admin/super', methods=['GET', 'POST'])
def super_admin():
    # 1. Handle Login Attempt
    if request.method == 'POST':
        # SECURITY: Pull from .env
        ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASS")
        
        if not ADMIN_PASSWORD:
            logger.critical("SUPER_ADMIN_PASS environment variable is missing!")
            flash("CRITICAL ERROR: Admin environment not configured safely.", "error")
            return redirect(url_for('super_admin'))

        entered_password = request.form.get('password')

        if entered_password == ADMIN_PASSWORD:
            session['is_super_admin'] = True
            session.permanent = False  # Forces session to expire when browser closes
            flash("Welcome to God Mode, Creator.", "success")
            return redirect(url_for('super_admin'))
        else:
            logger.warning(f"Failed God Mode login attempt from IP: {request.remote_addr}")
            flash("Access Denied. Incorrect Master Password.", "error")
            return redirect(url_for('super_admin'))
        
    # 2. Gatekeeper: Ensure only authenticated admins can see the dashboard
    if not session.get('is_super_admin'):
        return render_template('super_admin.html', logged_in=False)

    # 3. Load Dashboard Data
    try:
        # Fetch Core Data
        all_profiles = db.reference('profiles').get() or {}
        all_restaurants = db.reference('restaurants').get() or {}
        alerts_dict = db.reference('admin_alerts').get() or {}
        
        # Fetch Support System Data
        feedbacks_dict = db.reference('feedbacks').get() or {}
        call_requests_dict = db.reference('call_requests').get() or {}
        
        # Fetch System Settings for Marketing
        system_settings = db.reference('system_settings').get() or {}
        promo_active = system_settings.get('new_user_promo', False)
        
        # Calculate Analytics & Revenue
        total_users = sum(1 for p in all_profiles.values() if isinstance(p, dict)) 
        student_revenue = sum(20 for p in all_profiles.values() if isinstance(p, dict) and p.get('is_paid'))
        b2b_revenue = sum(2000 for r in all_restaurants.values() if isinstance(r, dict) and r.get('subscription_active'))
        total_revenue = student_revenue + b2b_revenue

        # --- CATEGORIZE USERS FOR THE FRONTEND TABS ---
        unpaid_users = []
        premium_users = []
        unverified_users = []

        for uid, user_data in all_profiles.items():
            if isinstance(user_data, dict):
                # Inject the ID into the dictionary so HTML can use it for deletion loops
                user_data['id'] = uid 
                
                is_verified = user_data.get('is_verified', False)
                has_paid = user_data.get('is_paid', False)

                if not is_verified:
                    unverified_users.append(user_data)
                elif is_verified and not has_paid:
                    unpaid_users.append(user_data)
                elif is_verified and has_paid:
                    premium_users.append(user_data)

        # Format and Sort AI Alerts (Newest First)
        alerts = [{'alert_id': k, **v} for k, v in alerts_dict.items() if isinstance(v, dict)]
        alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Format and Sort Feedbacks (Combine Suggestions & Tickets)
        feedbacks = []
        suggestions = feedbacks_dict.get('suggestion', {})
        tickets = feedbacks_dict.get('ticket', {})
        
        if isinstance(suggestions, dict):
            feedbacks.extend([{'id': k, 'type': 'suggestion', **v} for k, v in suggestions.items() if isinstance(v, dict)])
        if isinstance(tickets, dict):
            feedbacks.extend([{'id': k, 'type': 'ticket', **v} for k, v in tickets.items() if isinstance(v, dict)])
            
        feedbacks.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Format and Sort Call Requests
        call_requests = [{'id': k, **v} for k, v in call_requests_dict.items() if isinstance(v, dict)]
        call_requests.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Filter Pending Businesses
        pending_businesses = [
            {'id': k, **v} for k, v in all_restaurants.items() 
            if isinstance(v, dict) and not v.get('subscription_active')
        ]

        # 🚀 THE FIX: Safely fetch Audit Logs and sort in Python to bypass Firebase Index errors
        logs_dict = db.reference('admin_audit_logs').get() or {}
        audit_logs = list(logs_dict.values()) if isinstance(logs_dict, dict) else []
        audit_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        audit_logs = audit_logs[:20] # Keep only the 20 most recent logs for the UI

        # Dummy Chart Data (You can replace this with a real DB query of signups per day later)
        chart_labels = ['6 Days Ago', '5 Days Ago', '4 Days Ago', '3 Days Ago', '2 Days Ago', 'Yesterday', 'Today']
        chart_data = [5, 12, 15, 22, 18, 30, 45]
        
        return render_template('super_admin.html', 
                               logged_in=True,
                               total_users=total_users,
                               total_revenue=total_revenue,
                               student_revenue=student_revenue,
                               b2b_revenue=b2b_revenue,
                               alerts=alerts,
                               feedbacks=feedbacks,
                               call_requests=call_requests,
                               pending_businesses=pending_businesses,
                               promo_active=promo_active,
                               unpaid_users=unpaid_users,
                               premium_users=premium_users,
                               unverified_users=unverified_users,
                               audit_logs=audit_logs,
                               chart_labels=chart_labels,
                               chart_data=chart_data)
                               
    except Exception as e:
        logger.error(f"God Mode Dashboard Error: {e}")
        return "Failed to load dashboard data.", 500
    
    
@app.route('/api/admin/action', methods=['POST'])
def admin_action():
    if not session.get('is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    action = data.get('action')
    target_id = data.get('target_id')
    
    try:
        if action == 'ban_user':
            user_data = db.reference(f'profiles/{target_id}').get()
            if user_data and user_data.get('email'):
                try:
                    send_admin_alert_email(
                        recipient_email=user_data.get('email'),
                        recipient_name=user_data.get('name', 'Student').split()[0],
                        action_type='ban',
                        reason="Violation of Community Guidelines and Terms of Service."
                    )
                except Exception as mail_err:
                    logger.warning(f"Could not send ban email: {mail_err}")
            
            # Wipes from DB
            db.reference(f'profiles/{target_id}').delete() 
            
            if data.get('alert_id'):
                db.reference(f"admin_alerts/{data.get('alert_id')}").delete()
            logger.info(f"GOD_MODE: User {target_id} banned.")
                
        elif action == 'approve_business':
            now_eat = datetime.now(EAT)
            expiry = (now_eat + timedelta(days=30)).isoformat()
            
            db.reference(f'restaurants/{target_id}').update({
                'subscription_active': True,
                'subscription_start': now_eat.isoformat(),
                'subscription_expiry': expiry
            })
            logger.info(f"GOD_MODE: Merchant {target_id} approved.")
            
        elif action == 'dismiss_alert':
            db.reference(f'admin_alerts/{target_id}').delete()
            
        elif action == 'resolve_feedback':
            feedback_type = data.get('alert_id') # Stored type in alert_id variable from JS
            if feedback_type and target_id:
                db.reference(f'feedbacks/{feedback_type}/{target_id}').delete()
                
        elif action == 'resolve_call':
            if target_id:
                db.reference(f'call_requests/{target_id}').delete()
                
        elif action == 'mark_premium':
            if target_id:
                db.reference(f'profiles/{target_id}').update({'is_paid': True})
                # 📜 AUDIT LOG
                log_ref = db.reference('admin_audit_logs').push()
                log_ref.set({
                    'action': f"Manually granted Premium to user: {target_id}",
                    'timestamp': datetime.now(EAT).strftime("%Y-%m-%d %H:%M:%S EAT"),
                    'admin_ip': request.remote_addr
                })
                
        elif action == 'toggle_promo':
            current_status = db.reference('system_settings/new_user_promo').get()
            new_status = not current_status
            db.reference('system_settings/new_user_promo').set(new_status)
            return jsonify({'success': True, 'new_status': new_status})
            
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Admin Action Error ({action}): {e}")
        return jsonify({'success': False, 'message': "Internal server error."}), 500

@app.route('/api/admin/broadcast', methods=['POST'])
def admin_broadcast():
    """Endpoint to trigger targeted or mass emails to users."""
    if not session.get('is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    target_group = data.get('target_group', 'all')
    specific_email = data.get('specific_email', '').strip().lower()
    target_class = data.get('target_class', '').strip().upper()  # 👈 Added Class Extractor
    subject = data.get('subject')
    message = data.get('message')
    
    if not subject or not message:
        return jsonify({'success': False, 'message': 'Subject and message required.'}), 400
        
    try:
        all_profiles = db.reference('profiles').get() or {}
        
        # 👈 Updated function to accept specific_cls
        def dispatch_emails(profiles, target, specific_mail, specific_cls, subj, msg):
            success_count = 0
            for uid, user_data in profiles.items():
                if not isinstance(user_data, dict):
                    continue
                    
                email = user_data.get('email')
                if not email:
                    continue

                name = user_data.get('name', 'Student').split(' ')[0]
                is_verified = user_data.get('is_verified', False)
                is_paid = user_data.get('is_paid', False)
                user_class = user_data.get('class_code', '').upper() # 👈 Extracted class code

                should_send = False
                
                if target == 'all':
                    should_send = True
                elif target == 'class' and user_class == specific_cls: # 👈 Added Class Targeting
                    should_send = True
                elif target == 'premium' and is_verified and is_paid:
                    should_send = True
                elif target == 'verified_unpaid' and is_verified and not is_paid:
                    should_send = True
                elif target == 'unverified' and not is_verified:
                    should_send = True
                elif target == 'specific' and email.lower() == specific_mail:
                    should_send = True

                if should_send:
                    try:
                        send_broadcast_email(email, name, subj, msg)
                        success_count += 1
                    except Exception as email_err:
                        logger.warning(f"Failed sending to {email}: {email_err}")
            
            logger.info(f"GOD_MODE: Broadcast '{subj}' sent to {success_count} users in group '{target}'.")

        # Process in background so the UI doesn't freeze
        # 👈 Added target_class to the arguments passed to the background task
        socketio.start_background_task(dispatch_emails, all_profiles, target_group, specific_email, target_class, subject, message)
        
        return jsonify({'success': True, 'message': 'Broadcast queued for dispatch.'})
        
    except Exception as e:
        logger.error(f"Broadcast Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/admin/search_user', methods=['POST'])
def admin_search_user():
    """Allows Super Admin to lookup users by ID/Reg Number, Email, OR view specific filtered lists."""
    if not session.get('is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
    data = request.json
    query = data.get('query', '').strip().lower()
    
    if not query:
        return jsonify({'success': False, 'message': 'Search query required'}), 400
        
    try:
        all_profiles = db.reference('profiles').get() or {}
        matched_users = []
        
        safe_query_id = query.upper().replace('/', '_')
        
        for user_id, user_data in all_profiles.items():
            if isinstance(user_data, dict):
                user_email = user_data.get('email', '').lower()
                is_verified = user_data.get('is_verified', False)
                has_paid = user_data.get('is_paid', False)
                
                matches = False
                
                if query == 'all':
                    matches = True
                elif query == 'filter:unverified':
                    matches = not is_verified
                elif query == 'filter:unpaid':
                    matches = is_verified and not has_paid
                elif query == 'filter:paid':
                    matches = is_verified and has_paid
                elif user_id.upper() == safe_query_id or query in user_email:
                    matches = True
                
                if matches:
                    safe_data = {
                        'name': user_data.get('name', 'Unknown'),
                        'reg_number': user_data.get('reg_number', user_id),
                        'email': user_data.get('email', 'No email'),
                        'is_verified': is_verified,
                        'has_paid': has_paid,
                        'is_locked': user_data.get('is_locked', False)
                    }
                    matched_users.append(safe_data)

        if matched_users:
            matched_users.sort(key=lambda x: x.get('email', ''))
            return jsonify({'success': True, 'users': matched_users})
        else:
            return jsonify({'success': False, 'message': 'No users found matching that criteria.'})
            
    except Exception as e:
        logger.error(f"Search User Error: {e}")
        return jsonify({'success': False, 'message': 'Database error'}), 500


@app.route('/admin/ledger')
def admin_ledger():
    if not session.get('is_super_admin'):
        return redirect(url_for('home'))

    try:
        profiles = db.reference('profiles').get() or {}
        restaurants = db.reference('restaurants').get() or {}
        
        paid_students = [p for p in profiles.values() if isinstance(p, dict) and p.get('is_paid')]
        student_revenue = len(paid_students) * 20
        
        active_merchants = [r for r in restaurants.values() if isinstance(r, dict) and r.get('subscription_active')]
        merchant_revenue = len(active_merchants) * 2000
        
        total_revenue = student_revenue + merchant_revenue
        current_time_eat = datetime.now(EAT).strftime("%Y-%m-%d %H:%M EAT")

        return render_template('admin_ledger.html', 
                               student_count=len(paid_students),
                               student_rev=student_revenue,
                               merchant_count=len(active_merchants),
                               merchant_rev=merchant_revenue,
                               total_rev=total_revenue,
                               last_updated=current_time_eat)
    except Exception as e:
        logger.error(f"Admin Ledger Error: {e}")
        return "Failed to load ledger.", 500


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_super_admin', None)
    flash("Securely logged out of Command Center.", "info")
    return redirect(url_for('super_admin'))


# ==========================================
# 🚨 DESTRUCTIVE MASS ACTIONS (HTML FORMS)
# ==========================================

@app.route('/admin/delete_user/<user_id>', methods=['POST'])
def admin_delete_user(user_id):
    """Deletes a single specific user from the database."""
    if not session.get('is_super_admin'):
        return redirect(url_for('home'))
        
    try:
        db.reference(f'profiles/{user_id}').delete()
        flash(f"User {user_id} permanently deleted.", "success")
    except Exception as e:
        flash(f"Error deleting user: {str(e)}", "error")
        
    return redirect(url_for('super_admin'))

@app.route('/admin/delete_class', methods=['POST'])
def admin_delete_class():
    """Wipes all users belonging to a specific class code."""
    if not session.get('is_super_admin'):
        return redirect(url_for('home'))
        
    class_code = request.form.get('class_code', '').strip().upper()
    
    if not class_code:
        flash("You must specify a class code.", "error")
        return redirect(url_for('super_admin'))
        
    try:
        # Fetch all profiles and filter manually to avoid complex indexing
        profiles_ref = db.reference('profiles').get() or {}
        deleted_count = 0
        
        for uid, user_data in profiles_ref.items():
            if isinstance(user_data, dict) and user_data.get('class_code', '').upper() == class_code:
                db.reference(f'profiles/{uid}').delete()
                deleted_count += 1
                
        flash(f"Purge complete: {deleted_count} users in class {class_code} have been deleted.", "warning")
    except Exception as e:
        logger.error(f"Class Purge Error: {e}")
        flash("An error occurred while deleting the class.", "error")
        
    return redirect(url_for('super_admin'))

@app.route('/admin/delete_all', methods=['POST'])
def admin_delete_all_users():
    """THE NUCLEAR OPTION: Wipes the entire student database."""
    if not session.get('is_super_admin'):
        return redirect(url_for('home'))
    
    # ⚠️ ACTIVATED NUCLEAR OPTION ⚠️
    try:
        db.reference('profiles').delete()
        flash("NUCLEAR OPTION EXECUTED: Entire user database wiped clean.", "danger")
    except Exception as e:
        logger.error(f"Nuclear Option Error: {e}")
        flash("System failed to execute full wipe.", "error")
        
    return redirect(url_for('super_admin'))
import io
import csv
from flask import Response

# ==========================================
# 🚀 ENTERPRISE ADMIN FEATURES
# ==========================================

@app.route('/admin/export_csv')
def admin_export_csv():
    """Generates an Excel-compatible CSV file of users based on their status."""
    if not session.get('is_super_admin'):
        return redirect(url_for('home'))

    list_type = request.args.get('type', 'all')
    all_profiles = db.reference('profiles').get() or {}

    # Setup CSV writing in memory
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['User ID', 'Full Name', 'Email Address', 'Class Code', 'Account Status'])

    for uid, user in all_profiles.items():
        if not isinstance(user, dict):
            continue

        is_verified = user.get('is_verified', False)
        is_paid = user.get('is_paid', False)

        # Filter based on what tab the admin clicked "Export" on
        if list_type == 'unverified' and is_verified: continue
        if list_type == 'unpaid' and (not is_verified or is_paid): continue
        if list_type == 'premium' and not is_paid: continue

        # Determine readable status
        if is_paid:
            status = "Premium"
        elif is_verified:
            status = "Verified (Unpaid)"
        else:
            status = "Unverified"

        cw.writerow([
            uid,
            user.get('name', 'Unknown'),
            user.get('email', 'No Email'),
            user.get('class_code', 'N/A'),
            status
        ])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=mmust_users_{list_type}.csv"}
    )

@app.route('/api/admin/bulk_action', methods=['POST'])
def admin_bulk_action():
    """Handles executing a single action across dozens of selected items at once."""
    if not session.get('is_super_admin'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    data = request.json
    action = data.get('action')
    item_ids = data.get('item_ids', [])

    if not item_ids:
        return jsonify({'success': False, 'message': 'No items selected.'})

    try:
        for item_id in item_ids:
            if action == 'delete_users':
                db.reference(f'profiles/{item_id}').delete()
            elif action == 'mark_premium':
                db.reference(f'profiles/{item_id}').update({'is_paid': True})
            elif action == 'dismiss_alerts':
                db.reference(f'admin_alerts/{item_id}').delete()
            elif action == 'approve_biz':
                now_eat = datetime.now(EAT)
                expiry = (now_eat + timedelta(days=30)).isoformat()
                db.reference(f'restaurants/{item_id}').update({
                    'subscription_active': True,
                    'subscription_start': now_eat.isoformat(),
                    'subscription_expiry': expiry
                })

        # 📜 SECURE AUDIT LOG
        # Records who did what, and when.
        log_ref = db.reference('admin_audit_logs').push()
        log_ref.set({
            'action': f"Executed Bulk Action: '{action}' on {len(item_ids)} items.",
            'timestamp': datetime.now(EAT).strftime("%Y-%m-%d %H:%M:%S EAT"),
            'admin_ip': request.remote_addr
        })

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Bulk Action Error: {e}")
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/admin/load_more')
def admin_load_more():
    """Server-side pagination endpoint to prevent browser freezing with 5,000+ users."""
    if not session.get('is_super_admin'):
        return jsonify({'success': False}), 403
        
    list_type = request.args.get('type')
    offset = int(request.args.get('offset', 50))
    
    # NOTE: To fully implement this, you slice the dictionary here and return an HTML string.
    # For now, we return 'has_more: False' to hide the button so it doesn't throw a 404 error.
    return jsonify({'success': True, 'html': '', 'has_more': False})


# ==========================================
# API ENDPOINTS (SWIPE, PAYMENTS, NOTIFICATIONS)
# ==========================================
def ai_wingman_match_intro(user_id, partner_profile):
    """AI Wingman analyzes the match and sends the user a tip on how to start the chat."""
    try:
        partner_name = partner_profile.get('name', 'your match').split(' ')[0]
        partner_bio = partner_profile.get('bio', 'No bio provided.')
        
        # Craft a prompt for the Wingman
        prompt = (
            f"I just matched with {partner_name}. Their bio says: '{partner_bio}'. "
            f"Give me one short, funny, and clever opening line I can use. "
            f"Make it relevant to their bio. Keep it to one sentence."
        )
        
        # Get AI response
        ai_tip = get_ai_companion_response(prompt)
        
        # Format the system message
        wingman_msg = f"🕶️ **WINGMAN TIP:** You and {partner_name} are a great match! Try this opener: \"{ai_tip}\""
        
        # Save this as a message from the AI_COMPANION to the user
        save_chat_message('AI_COMPANION', user_id, wingman_msg, msg_type='text')
        
        # Emit it live so it pops up in their UI if they are looking at matches
        socketio.emit('receive_message', {
            'sender': 'AI_COMPANION',
            'text': wingman_msg,
            'type': 'text',
            'timestamp': datetime.now(EAT).isoformat()
        }, to=user_id)
        
    except Exception as e:
        logger.error(f"Wingman Match Intro Error: {e}")
        
@app.route('/api/profiles')
def get_profiles():
    user_id = request.args.get('user_id')
    ranked_deck = generate_ranked_deck(user_id)
    return jsonify(ranked_deck)

@app.route('/api/swipe', methods=['POST'])
@login_required
def record_swipe():
    data = request.json
    current_user_id = session.get('user_id')
    target_user_id = data.get('target_id')
    action = data.get('action') 
    timestamp = datetime.now(EAT).isoformat()

    if not target_user_id or not action:
        return jsonify({"status": "error", "message": "Missing swipe data"}), 400

    try:
        # 1. Record the swipe
        db.reference(f'swipes/{current_user_id}/{target_user_id}').set({
            'action': action,
            'timestamp': timestamp
        })
        
        is_match = False
        match_details = {}

        if action == 'like':
            # Fetch profiles early so we can compare them for cool commonalities!
            current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
            target_profile = db.reference(f'profiles/{target_user_id}').get() or {}

            # 2. CHECK ALL MATCH CONDITIONS
            # A: Did they already swipe right on us?
            target_swipe = db.reference(f'swipes/{target_user_id}/{current_user_id}').get()
            target_swiped_right = target_swipe and target_swipe.get('action') == 'like'
            
            # B: Do they have a pending Secret Crush on us?
            target_crush = db.reference(f'secret_crushes/{target_user_id}/{current_user_id}').get()
            target_crushed_on_me = target_crush and target_crush.get('status') == 'pending'

            # If either condition is true, IT IS A MATCH!
            if target_swiped_right or target_crushed_on_me:
                is_match = True
                match_id = "_".join(sorted([current_user_id, target_user_id]))
                
                # If they matched via crush, update the crush database to keep it clean
                if target_crushed_on_me:
                    db.reference(f'secret_crushes/{target_user_id}/{current_user_id}').update({'status': 'matched'})
                    db.reference(f'secret_crushes/{current_user_id}/{target_user_id}').set({'timestamp': timestamp, 'status': 'matched'})
                
                # 3. FIGURE OUT *WHY* THEY MATCHED (To make the UI awesome)
                match_reason = "You both liked each other! ✨"
                
                if target_crushed_on_me:
                    match_reason = "OMG! They had a Secret Crush on you! 🤫❤️"
                elif current_profile.get('intent') and current_profile.get('intent') != 'none' and current_profile.get('intent') == target_profile.get('intent'):
                    # They have the exact same relationship intent!
                    intent_map = {'coffee': '☕ Coffee', 'study': '📚 Study Sessions', 'event': '🎉 Events', 'relationship': '💘 A Relationship'}
                    shared_intent = intent_map.get(current_profile.get('intent'), '')
                    if shared_intent:
                        match_reason = f"You are both looking for {shared_intent}!"
                else:
                    # Let's check for shared words in their bios!
                    my_bio_words = set(current_profile.get('bio', '').lower().replace('.', '').replace(',', '').split())
                    their_bio_words = set(target_profile.get('bio', '').lower().replace('.', '').replace(',', '').split())
                    # Filter out boring words
                    stop_words = {'i', 'am', 'a', 'the', 'and', 'to', 'for', 'in', 'of', 'my', 'is', 'at', 'on', 'with', 'student', 'mmust', 'like', 'love', 'looking', 'here'}
                    common_words = (my_bio_words & their_bio_words) - stop_words
                    
                    if common_words:
                        best_word = list(common_words)[0].capitalize()
                        match_reason = f"You both mentioned '{best_word}' in your bios! 🎯"

                # 4. Save Match Entry to Database
                db.reference(f'matches/{match_id}').set({
                    'users': {current_user_id: True, target_user_id: True},
                    'matched_at': timestamp,
                    'last_message': 'You matched! Say hi.',
                    'last_message_time': timestamp,
                    'match_reason': match_reason # Save it so we can show it in chats later!
                })
                
                # 5. Prepare details for frontend popup
                match_details = {
                    'name': target_profile.get('name', 'Your Match').split(' ')[0],
                    'img': target_profile.get('img', '/static/img/placeholder.png'),
                    'bio': target_profile.get('bio', 'MMUST Student'),
                    'reason': match_reason # Pass the cool reason to the frontend UI
                }

                # 6. TRIGGER PUSH NOTIFICATION (Normal match buzz)
                current_name = current_profile.get('name', 'Someone').split(' ')[0]
                socketio.start_background_task(trigger_match_notification, target_user_id, current_name)

                # 7. THE AI MAGIC: AI Wingman sends a tip to the current user
                socketio.start_background_task(ai_wingman_match_intro, current_user_id, target_profile)

        return jsonify({
            "status": "success",
            "match": is_match,
            "match_details": match_details
        })

    except Exception as e:
        logger.error(f"Swipe Error: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500
      
@app.route('/api/save_subscription', methods=['POST'])
def save_subscription():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    subscription_data = request.json
    user_id = session.get('user_id')

    try:
        db.reference(f'push_subscriptions/{user_id}').set(subscription_data)
        return jsonify({"status": "success", "message": "Subscription saved to Firebase"})
    except Exception as e:
        logger.error(f"Error saving subscription: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500

@app.route('/api/end_date', methods=['POST'])
def end_date():
    if 'user_id' not in session: 
        return jsonify({'error': 'Unauthorized'}), 403
    
    user_id = session.get('user_id')
    partner_id = request.json.get('partner_id')
    
    if terminate_connection(user_id, partner_id):
        flash("Date terminated. All data and chats have been securely deleted.", "success")
        return jsonify({'success': True})
    return jsonify({'success': False}), 500
# ==========================================
# M-PESA B2C: STUDENT SUBSCRIPTIONS
# ==========================================

@app.route('/api/pay_student_fee', methods=['POST'])
@limiter.limit("3 per minute") # 🚨 STOPS STK PUSH SPAM
def pay_student_fee():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    phone_number = request.json.get('phone_number')
    user_id = session.get('user_id')

    if not phone_number or not phone_number.startswith("254") or len(phone_number) != 12:
        return jsonify({'success': False, 'message': 'Phone format must be 2547XXXXXXXX'}), 400

    base_url = "https://www.findyourmatch.co.ke"
    callback_url = f"{base_url}/api/mpesa/student_callback"
    
    response = initiate_stk_push(phone_number, 20, user_id, callback_url)

    if 'error' in response:
        return jsonify({'success': False, 'message': 'Payment failed to initiate. Try again.'})

    if 'CheckoutRequestID' in response:
        checkout_id = response['CheckoutRequestID']
        db.reference(f'pending_payments/{checkout_id}').set(user_id)
        return jsonify({'success': True, 'message': 'Check your phone for the M-Pesa PIN prompt!'})
    
    return jsonify({'success': False, 'message': 'Payment failed to initiate.'})

@app.route('/api/mpesa/student_callback', methods=['POST'])
@limiter.exempt # Webhooks shouldn't be rate-limited by user IP rules
def mpesa_student_callback():
    # 🚨 CRITICAL FIX: Block fake Postman payloads
    client_ip = get_real_ip()
    if not is_safaricom_ip(client_ip):
        logger.critical(f"🚨 FAKE MPESA CALLBACK BLOCKED! Origin IP: {client_ip}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Unauthorized IP. Go away hacker."}), 403

    data = request.json
    try:
        stk_callback = data['Body']['stkCallback']
        result_code = stk_callback['ResultCode']
        checkout_id = stk_callback['CheckoutRequestID']

        if result_code == 0:
            metadata = stk_callback['CallbackMetadata']['Item']
            mpesa_receipt = next((item['Value'] for item in metadata if item['Name'] == 'MpesaReceiptNumber'), None)
            
            pending_ref = db.reference(f'pending_payments/{checkout_id}')
            user_id = pending_ref.get()

            if user_id:
                expiry_date = (datetime.now(EAT) + timedelta(days=30)).isoformat()
                db.reference(f'profiles/{user_id}').update({
                    'is_paid': True,
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': mpesa_receipt
                })
                pending_ref.delete()
                logger.info(f"✅ STUDENT ACTIVATED: {user_id} paid via {mpesa_receipt}")
        else:
            fail_reason = stk_callback.get('ResultDesc', 'Unknown Error')
            logger.info(f"❌ STUDENT PAYMENT FAILED: {fail_reason}")

    except Exception as e:
        logger.error(f"⚠️ Student Callback Error: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})



# ==========================================
# M-PESA B2B: MERCHANT SUBSCRIPTIONS
# ==========================================

@app.route('/api/pay_subscription', methods=['POST'])
def pay_subscription():
    # 🚨 CRITICAL FIX 1: Use 'role' instead of 'account_type'
    if session.get('role') != 'business':
        return jsonify({'error': 'Unauthorized. Please log in as a merchant.'}), 403

    data = request.json
    phone_number = data.get('phone_number')
    
    # 🚨 CRITICAL FIX 2: Use 'user_id' instead of 'business_id'
    restaurant_id = session.get('user_id')

    if not phone_number or not phone_number.startswith("254") or len(phone_number) != 12:
        return jsonify({'error': 'Format must be 2547XXXXXXXX'}), 400

    base_url = "https://www.findyourmatch.co.ke"
    callback_url = f"{base_url}/api/mpesa/b2b_callback"
    
    # Initiate the STK Push request to Safaricom
    response = initiate_stk_push(phone_number, 2000, restaurant_id, callback_url)

    if 'error' in response:
        logger.error(f"STK Push Failed: {response.get('error')}")
        return jsonify({'success': False, 'message': 'Payment initiation failed. Try again.'})
    
    if 'CheckoutRequestID' in response:
        checkout_id = response['CheckoutRequestID']
        # Securely link the transaction to the merchant in Firebase
        db.reference(f'pending_b2b_payments/{checkout_id}').set(restaurant_id)
        return jsonify({'success': True, 'message': 'STK Push sent! Enter your M-Pesa PIN.'})

    return jsonify({'success': False, 'message': 'Payment failed to initiate.'})


@app.route('/api/mpesa/b2b_callback', methods=['POST'])
def mpesa_b2b_callback():
    """WEBHOOK: Safaricom hits this URL when a B2B payment completes."""
    data = request.get_json()
    if not data:
        return "No data", 400

    try:
        stk_callback = data['Body']['stkCallback']
        result_code = stk_callback['ResultCode']
        checkout_id = stk_callback['CheckoutRequestID']
        
        if result_code == 0:
            metadata = stk_callback['CallbackMetadata']['Item']
            amount = next((item['Value'] for item in metadata if item['Name'] == 'Amount'), None)
            receipt = next((item['Value'] for item in metadata if item['Name'] == 'MpesaReceiptNumber'), None)
            phone = next((item['Value'] for item in metadata if item['Name'] == 'PhoneNumber'), None)
            
            # 🚨 CRITICAL FIX 3: Use EAT (East Africa Time) to ensure accurate Kenyan timestamps
            current_time_eat = datetime.now(EAT).isoformat()

            # 1. Save to Financial Ledger
            db.reference('ledger').push({
                'type': 'B2B',
                'amount': amount,
                'receipt': receipt,
                'phone': phone,
                'timestamp': current_time_eat,
                'status': 'Completed'
            })
            logger.info(f"💰 M-Pesa B2B Payment Received: {amount} KSH (Receipt: {receipt})")

            # 2. ACTIVATE THE MERCHANT
            pending_ref = db.reference(f'pending_b2b_payments/{checkout_id}')
            restaurant_id = pending_ref.get()

            if restaurant_id:
                # Add exactly 30 days using the EAT timezone
                expiry_date = (datetime.now(EAT) + timedelta(days=30)).isoformat()
                
                db.reference(f'restaurants/{restaurant_id}').update({
                    'subscription_active': True,
                    'subscription_start': current_time_eat, # Good to track when it started
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': receipt
                })
                
                # Clean up the pending payment record
                pending_ref.delete()
                logger.info(f"✅ MERCHANT ACTIVATED: ID {restaurant_id}")
            else:
                logger.warning(f"⚠️ Payment received, but could not find matching merchant for checkout: {checkout_id}")

        else:
            fail_reason = stk_callback.get('ResultDesc', 'Unknown Error')
            logger.info(f"❌ M-Pesa B2B Payment Failed: {fail_reason}")

        # Always return a 0 response to Safaricom so they stop retrying the webhook
        return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

    except Exception as e:
        logger.error(f"Error processing B2B M-Pesa Callback: {e}")
        return jsonify({"ResultCode": 1, "ResultDesc": "Internal Error"}), 500
    
# ==========================================
# WEBSOCKETS (CHAT, AI COMPANION & SAFETY)
# ==========================================
import logging
from datetime import datetime
from flask import session, request
from flask_socketio import emit, join_room

# Ensure your database tools are imported
# from your_database_file import db, save_chat_message, get_ai_companion_response, analyze_safety, contains_phone_number

logger = logging.getLogger(__name__)

# ==========================================
# CONNECTION & STATUS TRACKING
# ==========================================
@socketio.on('connect')
def handle_connect():
    """Security Step: Join a private room and set status to ONLINE."""
    user_id = session.get('user_id')
    if user_id:
        join_room(user_id)
        try:
            # Broadcast to everyone that this user is online
            db.reference(f'profiles/{user_id}').update({'is_online': True})
            emit('status_change', {'user_id': user_id, 'is_online': True}, broadcast=True)
            logger.info(f"User {user_id} connected to WebSockets.")
        except Exception as e:
            logger.error(f"Presence update failed on connect: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    """Handle user disconnect and set status to OFFLINE."""
    user_id = session.get('user_id')
    if user_id:
        try:
            db.reference(f'profiles/{user_id}').update({'is_online': False})
            emit('status_change', {'user_id': user_id, 'is_online': False}, broadcast=True)
            logger.info(f"User {user_id} disconnected from WebSockets.")
        except Exception as e:
            logger.error(f"Presence update failed on disconnect: {e}")

# ==========================================
# TYPING INDICATOR
# ==========================================
@socketio.on('typing')
def handle_typing(data):
    """Routes the typing indicator instantly."""
    receiver_id = data.get('receiver_id')
    if receiver_id:
        # Route directly to the receiver's private room
        emit('user_typing', data, to=receiver_id)

# ==========================================
# MESSAGE ROUTING
# ==========================================
# ==========================================
# MESSAGE ROUTING & DB SAVING
# ==========================================
@socketio.on('send_message')
def handle_message(data):
    # 1. SECURITY: Get the sender's ID
    sender_id = session.get('user_id')
    if not sender_id:
        logger.warning("Unauthorized message attempt (no session).")
        return 

    # 2. VALIDATION: Prevent empty ghost messages
    receiver_id = data.get('receiver_id')
    msg_text = data.get('text', '').strip()
    msg_type = data.get('type', 'text')
    temp_id = data.get('temp_id') # Crucial for the ✓✓ frontend confirmation

    if not receiver_id or not msg_text:
        return

    now_eat = datetime.now(EAT).isoformat()
    data['sender'] = sender_id
    data['timestamp'] = now_eat

    # ------------------------------------------
    # ROUTE A: AI COMPANION LOGIC
    # ------------------------------------------
    if receiver_id == 'AI_COMPANION':
        # Emit to sender's room so all their open tabs stay in sync
        emit('receive_message', data, to=sender_id)
        emit('user_typing', {'sender': 'AI_COMPANION', 'is_typing': True}, to=sender_id)
        
        current_user_gender = "unknown"
        try:
            user_profile = db.reference(f'profiles/{sender_id}').get()
            if user_profile and 'gender' in user_profile:
                current_user_gender = user_profile['gender']
        except Exception:
            pass
        
        def ai_worker(query, user_room, gender):
            try:
                ai_reply = get_ai_companion_response(query, user_gender=gender)
                socketio.emit('user_typing', {'sender': 'AI_COMPANION', 'is_typing': False}, to=user_room)
                socketio.emit('receive_message', {
                    'sender': 'AI_COMPANION',
                    'type': 'text',
                    'text': ai_reply,
                    'timestamp': datetime.now(EAT).isoformat()
                }, to=user_room)
            except Exception as e:
                logger.error(f"AI Worker Error: {e}")

        socketio.start_background_task(ai_worker, msg_text, sender_id, current_user_gender)
        return

    # ------------------------------------------
    # ROUTE B: HUMAN-TO-HUMAN SAFETY MODERATION
    # ------------------------------------------
    if msg_type == 'text':
        try:
            safety_check = analyze_safety(msg_text)
            
            if not safety_check.get('is_safe', True):
                if safety_check.get('flag') in ['self_harm', 'violence']:
                    def save_alert(s_id, r_id, txt, flag):
                        try:
                            db.reference('admin_alerts').push({
                                'sender': s_id,
                                'receiver': r_id,
                                'message': txt,
                                'flag': flag,
                                'timestamp': datetime.now(EAT).isoformat()
                            })
                        except Exception as e:
                            logger.error(f"Alert save error: {e}")
                    
                    socketio.start_background_task(save_alert, sender_id, receiver_id, msg_text, safety_check['flag'])
                
                warning_msg = {'sender': 'SYSTEM_AI', 'type': 'text', 'text': safety_check.get('system_reply', 'Message flagged.')}
                emit('receive_message', warning_msg, to=sender_id) 
                return

            if contains_phone_number(msg_text):
                warning_msg = {
                    'sender': 'SYSTEM_AI',
                    'type': 'text',
                    'text': "SYSTEM ALERT: Sharing phone numbers is restricted for your safety."
                }
                emit('receive_message', warning_msg, to=sender_id) 
                return
                
        except Exception as e:
            logger.error(f"Safety Check Error: {e}")

    # ------------------------------------------
    # ROUTE C: DATABASE SAVING & DELIVERY
    # ------------------------------------------
    match_id = f"match_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    
    message_payload = {
        'sender_id': sender_id,
        'text': msg_text,
        'timestamp': now_eat,
        'type': msg_type,
        'status': 'sent'
    }

    try:
        # 1. Save to Firebase permanently
        new_msg_ref = db.reference(f'matches/{match_id}/messages').push(message_payload)
        
        # 2. Update the parent match node for the inbox sidebar sorting
        db.reference(f'matches/{match_id}').update({
            'last_message': msg_text,
            'last_message_time': now_eat,
            f'users/{sender_id}': True,
            f'users/{receiver_id}': True
        })

        # 3. Deliver to Receiver's screen
        emit('receive_message', {
            'sender': sender_id,
            'text': msg_text,
            'timestamp': now_eat,
            'temp_id': temp_id,
            'msg_id': new_msg_ref.key
        }, to=receiver_id)

        # 4. Deliver CONFIRMATION back to Sender's screen (Turns 🕒 to ✓✓)
        emit('receive_message', {
            'sender': sender_id,
            'temp_id': temp_id,
            'msg_id': new_msg_ref.key,
            'status': 'sent'
        }, to=sender_id)

    except Exception as e:
        logger.error(f"Failed to route and save message: {e}")
        # Optionally emit an error to the sender so they know it failed
        
# ==========================================
# STUDENT VENUE DISCOVERY & BOOKING
# ==========================================
@app.route('/discover')
@requires_subscription
def discover_venues():
    """THE DISCOVERY DECK FOR DATE VENUES WITH TRENDING HEATMAP"""
    user_id = session.get('user_id')
    
    try:
        # 1. Fetch only ACTIVE (paying) restaurants
        venues = get_all_restaurants(active_only=True)
        
        # ==========================================
        # 🔥 NEW: TRENDING VENUES ALGORITHM
        # ==========================================
        all_bookings = db.reference('bookings').get() or {}
        now_eat = datetime.now(EAT)
        seven_days_ago = now_eat - timedelta(days=7)
        
        # Initialize scores
        venue_scores = {str(v.get('id')): 0 for v in venues}
        
        # Tally up the bookings from the last 7 days
        for b_id, b_data in all_bookings.items():
            if not isinstance(b_data, dict): continue
            
            v_id = str(b_data.get('venue_id'))
            b_timestamp = b_data.get('timestamp') or b_data.get('created_at') # Fallback depending on how you save dates
            
            if v_id in venue_scores and b_timestamp:
                try:
                    b_time = datetime.fromisoformat(b_timestamp)
                    # Only count bookings from the last 7 days
                    if b_time >= seven_days_ago:
                        # Weight Approved/Completed dates heavier than Pending ones
                        points = 2 if b_data.get('status') in ['Approved', 'Completed'] else 1
                        venue_scores[v_id] += points
                except ValueError:
                    pass # Ignore badly formatted old dates
        
        # Attach the calculated score to the venue dictionaries
        for venue in venues:
            venue['trending_score'] = venue_scores.get(str(venue.get('id')), 0)
            
        # Create a separate list for the Top 3 Trending venues (Must have at least 1 booking to trend)
        trending_venues = sorted([v for v in venues if v['trending_score'] > 0], key=lambda x: x['trending_score'], reverse=True)[:3]

        # ==========================================
        # 2. Fetch student profiles for the invite dropdown
        # ==========================================
        all_profiles_dict = db.reference('profiles').get() or {}
        selectable_students = []

        for p_id, p in all_profiles_dict.items():
            # Skip conditions: Self, Hidden profiles, or the AI Wingman
            if not isinstance(p, dict) or p_id == user_id or not p.get('is_visible', True) or p_id == 'AI_COMPANION':
                continue
            
            # Calculate compatibility
            ai_score = p.get('ai_score', random.randint(60, 95))
            
            selectable_students.append({
                'id': p_id,
                'name': p.get('name', 'Student').split(' ')[0],
                'compatibility': ai_score,
                'is_perfect_match': ai_score >= 80
            })

        # Sort: Perfect Matches at the top, then by score
        selectable_students.sort(key=lambda x: (x['is_perfect_match'], x['compatibility']), reverse=True)

    except Exception as e:
        logger.error(f"Error loading discovery data: {e}")
        venues, trending_venues, selectable_students = [], [], []
        flash("Error loading page. Please refresh.", "error")
        
    return render_template(
        'bookings.html', 
        current_user=session.get('user_name', 'Student').split(' ')[0],
        venues=venues, 
        trending_venues=trending_venues, # <-- Pass trending venues to the template
        matches=selectable_students 
    )
    
    
@app.route('/api/propose_date', methods=['POST'])
@login_required
def propose_date():
    """Handles the booking request and sends a real-time invite in the chat."""
    data = request.json
    sender_id = session.get('user_id')
    sender_name = session.get('user_name', 'Your Match').split(' ')[0]
    
    venue_id = data.get('venue_id')
    venue_name = data.get('venue_name')
    partner_id = data.get('partner_id')
    date_day = data.get('day')
    date_time = data.get('time')
    
    # 1. Strict Validation Checks
    if not all([venue_id, partner_id, date_day, date_time]):
        return jsonify({'success': False, 'message': 'Missing details. Please fill out all fields.'}), 400
        
    # Prevent users from booking a table with the AI bot
    if partner_id == 'AI_COMPANION':
        return jsonify({'success': False, 'message': 'You cannot take the AI Wingman on a physical date!'}), 400
        
    try:
        # 2. Database Writes (Synchronous to ensure they succeed before responding)
        create_date_booking(venue_id, sender_id, partner_id, date_day, date_time)
        increment_restaurant_view(venue_id)
        
        # Format the chat invitation
        invite_msg = (
            f"💌 **DATE INVITATION** 💌\n\n"
            f"I'd love to take you to **{venue_name}**!\n"
            f"📅 **When:** {date_day} at {date_time}\n"
            f"Let me know if you're down!"
        )
        
        # Save the message to Firebase so it persists in their chat history
        save_chat_message(sender_id, partner_id, invite_msg, msg_type='date_invite')
        
        # 3. REAL-TIME SYNC (Offloaded to Background Task for 0ms UI latency)
        socket_payload = {
            'sender': sender_id,
            'receiver_id': partner_id,
            'type': 'date_invite',
            'text': invite_msg,
            'timestamp': datetime.now(EAT).isoformat(),
            'temp_id': f"invite_{int(datetime.now(EAT).timestamp())}"
        }
        
        def emit_date_notifications():
            try:
                # Push to the partner's screen so they see it instantly
                socketio.emit('receive_message', socket_payload, to=partner_id)
                # Push to the sender's OTHER devices (e.g., laptop) so they stay in sync
                socketio.emit('receive_message', socket_payload, to=sender_id)
            except Exception as sock_err:
                logger.warning(f"Socket emit failed (partner might be offline): {sock_err}")

        # Start the background task immediately
        socketio.start_background_task(emit_date_notifications)

        # 4. NOTIFY MERCHANT VIA EMAIL
        try:
            restaurant = get_restaurant(venue_id)
            if restaurant and restaurant.get('email'):
                user_a_name = session.get('user_name', 'Student').split(' ')[0]
                # Fetch partner name
                partner_profile = db.reference(f"profiles/{partner_id}").get() or {}
                user_b_name = partner_profile.get('name', 'Their Match').split(' ')[0]
                
                threading.Thread(target=send_date_request_to_merchant_email, args=(
                    restaurant['email'], 
                    restaurant.get('business_name', 'Merchant'),
                    user_a_name,
                    user_b_name,
                    date_day,
                    date_time
                )).start()
        except Exception as e:
            logger.warning(f"Failed to send email to merchant: {e}")

        return jsonify({'success': True, 'message': 'Invitation sent!'})
        
    except Exception as e:
        logger.error(f"Error proposing date: {e}")
        return jsonify({'success': False, 'message': 'Internal server error.'}), 500
# ==========================================
# AI WINGMAN & RIZZ CHECK ROUTES
# ==========================================

@app.route('/wingman')
@login_required
def ai_wingman():
    """Renders the AI Wingman dashboard."""
    user_id = session.get('user_id')
    
    try:
        user_profile = db.reference(f'profiles/{user_id}').get() or {}
        
        # Fetch all matches
        raw_matches = get_user_matches(user_id) 
        
        # 🛡️ Filter out the AI bot so users can't generate icebreakers to talk to the robot!
        clean_matches = [m for m in raw_matches if m.get('id') != 'AI_COMPANION']
        
        return render_template('wingman.html', user=user_profile, matches=clean_matches)
        
    except Exception as e:
        logger.error(f"Wingman Page Network Error: {e}")
        flash("Network connection dropped slightly. Please refresh the page.", "error")
        # Fallback to empty data to prevent a 500 Server Error crash
        return render_template('wingman.html', user={'bio': 'Network error.'}, matches=[])


@app.route('/api/wingman_action', methods=['POST'])
@login_required
@limiter.limit("5 per minute") # 🚨 STOPS BOT SPAMMING THE GROQ API
def api_wingman_action():
    """Handles requests for Profile Roasts and Icebreakers."""
    data = request.json
    action = data.get('action')
    user_id = session.get('user_id')
    
    try:
        # =======================================================
        # 1. PROFILE ROASTER LOGIC
        # =======================================================
        if action == 'roast_profile':
            user_profile = db.reference(f'profiles/{user_id}').get() or {}
            bio = user_profile.get('bio', 'No bio provided.')
            major = user_profile.get('major', 'Unknown major.')
            
            prompt = (
                f"Act as a brutally honest, funny, but ultimately helpful college dating coach. "
                f"My major is {major} and my dating app bio is: '{bio}'. "
                f"Give me a funny 'roast' of this bio, and then provide 3 actionable tips "
                f"or rewrite suggestions to make it more attractive to college students. "
                f"CRITICAL: Do not say 'Here is your roast'. Just start roasting immediately."
            )
            
            ai_response = get_ai_companion_response(prompt, user_gender=user_profile.get('gender', 'unknown'))
            return jsonify({'success': True, 'response': ai_response})
            
        # =======================================================
        # 2. SMART ICEBREAKER & CONVERSATION CONTINUER
        # =======================================================
        elif action == 'generate_icebreaker':
            partner_id = data.get('partner_id')
            if not partner_id:
                return jsonify({'success': False, 'message': 'Select a match first!'}), 400
                
            partner_profile = db.reference(f'profiles/{partner_id}').get() or {}
            partner_bio = partner_profile.get('bio', 'They have no bio... time to get creative.')
            partner_name = partner_profile.get('name', 'your match').split(' ')[0]
            
            # 🧠 READ THE ROOM: Fetch actual chat history to see if they are already talking!
            chat_history = get_chat_history(user_id, partner_id)
            human_chats = [msg for msg in chat_history if msg.get('sender') != 'SYSTEM_AI'] if chat_history else []
            
            if human_chats and len(human_chats) > 0:
                # 💬 REPLY MODE: They are already talking.
                recent_msgs = human_chats[-6:] # Grab the last 6 messages for context
                formatted_chat = ""
                for msg in recent_msgs:
                    sender_label = "Me" if msg['sender'] == user_id else partner_name
                    formatted_chat += f"{sender_label}: {msg.get('text', '')}\n"
                
                prompt = (
                    f"Act as my charismatic dating coach. I am currently chatting with {partner_name}. "
                    f"Their bio says: '{partner_bio}'.\n"
                    f"Here is the exact transcript of our recent conversation:\n"
                    f"{formatted_chat}\n\n"
                    f"Based EXACTLY on what we are talking about right now, write 3 brilliant, natural-sounding replies I can send next to keep the conversation engaging. "
                    f"Make them varied (1 funny/teasing, 1 thoughtful question, 1 smooth transition). "
                    f"CRITICAL RULE: Do NOT output conversational filler like 'Here are your options:' or 'Let's get this started'. "
                    f"Just output the 3 numbered options directly so I can copy and paste them."
                )
            else:
                # 🧊 COLD OPENER MODE: The chat is totally empty.
                prompt = (
                    f"Act as my ultimate wingman. I just matched with someone named {partner_name}. "
                    f"Their bio says: '{partner_bio}'. "
                    f"Generate 3 highly customized, funny, and engaging icebreakers I can send them right now based ONLY on their bio. "
                    f"Don't be creepy. Keep it fun and college-appropriate. "
                    f"CRITICAL RULE: Do NOT output conversational filler like 'Here are some options:' or 'Let's get this started'. "
                    f"Just output the 3 numbered options directly so I can copy and paste them."
                )
            
            ai_response = get_ai_companion_response(prompt, user_gender='unknown')
            return jsonify({'success': True, 'response': ai_response})
            
        else:
            return jsonify({'success': False, 'message': 'Invalid action.'}), 400

    except Exception as e:
        logger.error(f"Wingman API Error: {e}")
        return jsonify({'success': False, 'message': 'The Wingman is currently busy. Try again later!'}), 500

@app.route('/api/support/submit', methods=['POST'])
@login_required
def support_submit():
    """Professional Support & Feedback Route"""
    data = request.json
    user_id = session.get('user_id')
    support_type = data.get('type', 'feedback')
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'success': False, 'message': 'Message cannot be empty.'}), 400
        
    try:
        db.reference(f'feedbacks/{support_type}').push({
            'user_id': user_id,
            'user_name': session.get('user_name', 'Student'),
            'message': message,
            'timestamp': datetime.now(EAT).isoformat(),
            'status': 'open'
        })
        return jsonify({'success': True, 'message': 'Successfully submitted! Our team will review this shortly.'})
    except Exception as e:
        logger.error(f"Support API Error: {e}")
        return jsonify({'success': False, 'message': 'Failed to submit. Try again later.'}), 500

@app.route('/api/wingman/execute', methods=['POST'])
@login_required
@limiter.limit("5 per minute")
def wingman_execute():
    """Premium AI Wingman Route using Groq LLaMA-3"""
    data = request.json
    action = data.get('action') # 'roast' or 'icebreaker'
    user_id = session.get('user_id')
    
    try:
        user_profile = db.reference(f'profiles/{user_id}').get() or {}
        bio = user_profile.get('bio', 'No bio provided.')
        interests = user_profile.get('interests', 'No interests listed.')
        course = user_profile.get('course', user_profile.get('major', 'MMUST Student'))
        gender = user_profile.get('gender', 'unknown')

        if action == 'roast':
            prompt = (
                f"Act as a brutally honest but funny college dating coach. "
                f"Roast this MMUST student's profile: \n"
                f"Bio: {bio}\nInterests: {interests}\nCourse: {course}\n"
                f"Use Kenyan campus slang (comrade, rizz, character development). "
                f"Finish with 2 actionable tips for improvement. Keep it sharp and witty."
            )
        elif action == 'icebreaker':
            partner_id = data.get('partner_id')
            if not partner_id:
                return jsonify({'success': False, 'message': 'Please select a student first.'}), 400
            
            partner_profile = db.reference(f'profiles/{partner_id}').get() or {}
            p_name = partner_profile.get('name', 'Match').split()[0]
            p_bio = partner_profile.get('bio', 'No bio.')
            p_interests = partner_profile.get('interests', 'No interests listed.')
            
            prompt = (
                f"You are a smooth AI wingman. Generate 3 creative and funny icebreakers for {p_name} "
                f"based on their profile: \nBio: {p_bio}\nInterests: {p_interests}\n"
                f"Avoid generic 'Hey'. Use the details to be specific and engaging."
            )
        else:
            return jsonify({'success': False, 'message': 'Invalid action.'}), 400

        response = get_ai_companion_response(prompt, user_gender=gender)
        return jsonify({'success': True, 'response': response})

    except Exception as e:
        logger.error(f"Wingman Execute Error: {e}")
        return jsonify({'success': False, 'message': 'The AI Wingman is taking a break. Try again later.'}), 500

import hashlib

def hash_reg_number(reg_num):
    """
    Standardizes the reg number (removes spaces, makes uppercase)
    and returns an unbreakable SHA-256 hash.
    """
    if not reg_num: return None
    clean_reg = str(reg_num).strip().upper()
    # Add a "salt" (a secret key) to make it even harder to crack
    secret_salt = os.getenv("HASH_SALT", "MMUST_SECRET_2026")
    salted_reg = f"{clean_reg}_{secret_salt}"
    
    return hashlib.sha256(salted_reg.encode('utf-8')).hexdigest()
import string
import random

# Handle 404 Page Not Found errors globally
@app.errorhandler(404)
def page_not_found(e):
    # Renders your beautiful new 404 template, returning a 404 status code
    return render_template('404.html'), 404

# Optional: Handle 500 Internal Server Errors (if your code crashes)
@app.errorhandler(500)
def internal_server_error(e):
    # You can reuse the 404 template, or create a specific 500.html later
    return render_template('404.html'), 500


@app.route('/join')
def join():
    """Catches incoming referral links and stores the code before signup."""
    # Get the code from the URL (e.g., ?ref=MMUST-VIP-26)
    ref_code = request.args.get('ref')
    
    if ref_code:
        # Save it securely in their browser session
        session['referred_by'] = ref_code
        flash("✨ VIP Invite applied! Create your account to claim your free Premium week.", "success")
    
    # Send them to the signup page (Adjust 'auth.signup' if your signup is just 'signup')
    return redirect(url_for('auth.signup'))


@app.route('/referrals')
def referrals():
    if 'user_id' not in session:
        flash("Please log in to view your VIP Dashboard.", "error")
        return redirect(url_for('auth.login')) 
    
    user_id = session['user_id']
    user_ref = db.reference(f'profiles/{user_id}')
    user_data = user_ref.get()
    
    if not user_data:
        flash("Profile not found. Please log in again.", "error")
        session.pop('user_id', None)
        return redirect(url_for('auth.login'))
        
    # 1. Ensure Referral Code Exists
    if 'referral_code' not in user_data:
        first_name = user_data.get('name', 'VIP').split(' ')[0].upper()
        clean_name = ''.join(e for e in first_name if e.isalnum())[:5] 
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        new_ref_code = f"MMUST-{clean_name}-{random_suffix}"
        
        user_ref.update({'referral_code': new_ref_code})
        user_data['referral_code'] = new_ref_code
        
    # 2. Ensure Wingman Code Exists (NEW)
    if 'wingman_code' not in user_data:
        # Generates a short, clean 6-character hash for the URL
        wingman_hash = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        user_ref.update({'wingman_code': wingman_hash})
        user_data['wingman_code'] = wingman_hash
        
    user_data['referrals_count'] = user_data.get('referrals_count', 0)
    user_data['free_weeks_earned'] = user_data.get('free_weeks_earned', 0)

    # Determine the base URL dynamically
    base_url = "https://www.findyourmatch.co.ke"
    return render_template('referrals.html', user=user_data, base_url=base_url)

@app.route('/api/check_access', methods=['GET'])
@login_required
def check_access():
    """The frontend calls this every 3 seconds to see if the callback arrived."""
    user_id = session.get('user_id')
    
    # Check Firebase to see if the webhook flipped the switch
    user_data = db.reference(f'profiles/{user_id}').get()
    
    if user_data and user_data.get('is_paid') == True:
        return jsonify({'granted': True})
        
    return jsonify({'granted': False})

# ==========================================
# PUBLIC WINGMAN ROUTES (VIRAL GROWTH)
# ==========================================
@app.route('/bestie/<wingman_code>')
def bestie_review(wingman_code):
    """Public read-only route for a friend to review a profile."""
    # Find the user by their unique wingman code
    matching_users = db.reference('profiles').order_by_child('wingman_code').equal_to(wingman_code).get()
    
    if not matching_users:
        flash("This profile link has expired or doesn't exist.", "warning")
        return redirect(url_for('home'))
        
    # Extract the target user's ID and data
    target_id = list(matching_users.keys())[0]
    target_user = matching_users[target_id]
    
    # Hide sensitive data just in case
    safe_profile = {
        'name': target_user.get('name', 'Student').split(' ')[0],
        'age': target_user.get('age', 18),
        'bio': target_user.get('bio', 'No bio provided.'),
        'img': target_user.get('img', '/static/img/placeholder.png'),
        'major': target_user.get('major', 'MMUST Student'),
        'intent': target_user.get('intent', '')
    }
    
    return render_template('bestie_review.html', profile=safe_profile, target_id=target_id)

@app.route('/api/bestie_vote', methods=['POST'])
def bestie_vote():
    """Receives the 'Catch' or 'Red Flag' vote from the friend."""
    data = request.json
    target_id = data.get('target_id')
    vote = data.get('vote') # 'catch' or 'red_flag'
    
    if not target_id or not vote:
        return jsonify({'success': False}), 400
        
    try:
        # Send a real-time system message to the user!
        msg_text = "🔥 WINGMAN ALERT: Your bestie says you're a Catch!" if vote == 'catch' else "🚨 WINGMAN ALERT: Your bestie flagged your profile! Time to update your bio?"
        
        save_chat_message('SYSTEM_AI', target_id, msg_text, msg_type='text')
        
        # Attempt real-time socket delivery if they are online
        socketio.emit('receive_message', {
            'sender': 'SYSTEM_AI',
            'text': msg_text,
            'timestamp': datetime.now(EAT).isoformat()
        }, to=target_id)
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Bestie Vote Error: {e}")
        return jsonify({'success': False}), 500
    

@app.route('/merchant/dashboard')
@login_required # Ensure this user is a merchant, not a student
def merchant_dashboard():
    merchant_id = session.get('user_id')
    
    # 1. Fetch the merchant's specific restaurant data
    restaurant_ref = db.reference(f'restaurants/{merchant_id}').get()
    
    if not restaurant_ref:
        flash("Restaurant profile not found.", "error")
        return redirect(url_for('index'))

    # 2. Calculate ROI & Analytics
    all_bookings = db.reference('bookings').get() or {}
    total_bookings = 0
    completed_bookings = 0
    
    # We will assume an average spend of 1500 KSH per couple for the ROI calculation
    AVERAGE_COUPLE_SPEND_KSH = 1500 
    
    # Get the start of the current month for monthly stats
    now = datetime.now(EAT)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_completed = 0

    for b_id, b_data in all_bookings.items():
        if b_data.get('venue_id') == merchant_id:
            total_bookings += 1
            
            # Count how many dates actually happened (merchant scanned the QR code)
            if b_data.get('status') in ['Completed', 'Archived']:
                completed_bookings += 1
                
                # Check if it was this month
                b_timestamp = b_data.get('completed_timestamp')
                if b_timestamp:
                    try:
                        b_date = datetime.fromisoformat(b_timestamp)
                        if b_date >= start_of_month:
                            monthly_completed += 1
                    except ValueError:
                        pass # Ignore badly formatted old dates

    # Calculate the estimated revenue brought in by the app this month
    monthly_revenue_generated = monthly_completed * AVERAGE_COUPLE_SPEND_KSH
    
    # 3. Fetch Active Flash Perks
    active_perks = db.reference(f'flash_perks/{merchant_id}').get() or {}

    analytics = {
        'total_views': restaurant_ref.get('profile_views', 0),
        'total_bookings': total_bookings,
        'monthly_completed': monthly_completed,
        'monthly_revenue': f"KSH {monthly_revenue_generated:,}",
        'subscription_status': restaurant_ref.get('subscription_status', 'Inactive')
    }

    return render_template(
        'merchant_dashboard.html', 
        restaurant=restaurant_ref, 
        analytics=analytics,
        flash_perks=active_perks
    )
    
@app.route('/api/merchant/create_flash_perk', methods=['POST'])
@login_required
def create_flash_perk():
    merchant_id = session.get('user_id')
    data = request.json
    
    offer_text = data.get('offer_text') # e.g., "30% off for the next 5 couples!"
    max_claims = data.get('max_claims', 5) # How many couples can claim it
    expires_in_hours = data.get('expires_in', 2)
    
    if not offer_text:
        return jsonify({'success': False, 'message': 'Offer text is required.'}), 400
        
    try:
        # Calculate expiration time
        expiration_time = datetime.now(EAT) + timedelta(hours=int(expires_in_hours))
        
        perk_data = {
            'offer_text': offer_text,
            'max_claims': int(max_claims),
            'claims_used': 0,
            'created_at': datetime.now(EAT).isoformat(),
            'expires_at': expiration_time.isoformat(),
            'is_active': True
        }
        
        # Save to the database under this specific merchant
        # We use push() to generate a unique ID for this specific perk
        new_perk_ref = db.reference(f'flash_perks/{merchant_id}').push(perk_data)
        
        # Optional: You could trigger a WebSocket event here to instantly notify 
        # all online students that a new Flash Perk is available!
        
        return jsonify({'success': True, 'message': 'Flash Perk is live! ⚡'})
        
    except Exception as e:
        logger.error(f"Error creating Flash Perk: {e}")
        return jsonify({'success': False, 'message': 'Failed to create perk.'}), 500
    
# ==========================================
# SUPPORT, SUGGESTIONS & CALL REQUESTS
# ==========================================

@app.route('/api/submit_feedback', methods=['POST'])
@login_required
def submit_feedback():
    """Handles both System Suggestions and Support Tickets."""
    data = request.json
    user_id = session.get('user_id')
    
    # 'suggestion' or 'ticket'
    feedback_type = data.get('type', 'suggestion') 
    message = data.get('message', '').strip()
    
    if not message:
        return jsonify({'success': False, 'message': 'Message cannot be empty.'}), 400
        
    try:
        # Save to Firebase under a 'feedbacks' node
        db.reference(f'feedbacks/{feedback_type}').push({
            'user_id': user_id,
            'user_name': session.get('user_name', 'Student'),
            'message': message,
            'timestamp': datetime.now(EAT).isoformat(),
            'status': 'open' # Admins can mark this as 'resolved' later
        })
        
        return jsonify({'success': True, 'message': 'Successfully submitted! Thank you.'})
    except Exception as e:
        logger.error(f"Feedback Submission Error: {e}")
        return jsonify({'success': False, 'message': 'Failed to submit. Please try again.'}), 500

@app.route('/api/request_call', methods=['POST'])
@login_required
def request_call():
    """Allows users to request a phone call from the Support Team."""
    data = request.json
    user_id = session.get('user_id')
    phone_number = data.get('phone_number')
    reason = data.get('reason', 'General Support')

    if not phone_number:
        return jsonify({'success': False, 'message': 'Phone number is required.'}), 400

    try:
        db.reference('call_requests').push({
            'user_id': user_id,
            'user_name': session.get('user_name', 'Student'),
            'phone_number': phone_number,
            'reason': reason,
            'timestamp': datetime.now(EAT).isoformat(),
            'status': 'pending'
        })
        return jsonify({'success': True, 'message': 'Call request received! An admin will call you shortly.'})
    except Exception as e:
        logger.error(f"Call Request Error: {e}")
        return jsonify({'success': False, 'message': 'Failed to request call.'}), 500

import random

# ==========================================
# THE ICEBREAKER ENGINE (DAILY PROMPTS)
# ==========================================

# A list of spicy, fun, and campus-specific prompts
CAMPUS_PROMPTS = [
    # --- The Original 50 (Dating, Survival & Campus Culture) ---
    "What is the most overrated food spot outside MMUST?",
    "What is the biggest red flag in a university relationship?",
    "If you had 1000 KSH for a date in Kakamega, where are you going?",
    "Be honest: 8 AM classes or 5 PM classes?",
    "What's your most controversial opinion about MMUST comrades?",
    "Best place to hide and study when the library is full?",
    "What's a text you received that immediately gave you the 'ick'?",
    "Describe your perfect weekend in Kakamega.",
    "What is a fashion trend on campus that needs to stop immediately?",
    "Who is the strictest lecturer in your school?",
    "Is it a flex or a trap to date someone in your exact same class?",
    "Green flags you look for on a first date in Kakamega?",
    "What's the worst excuse you've used (or heard) to dodge a date?",
    "Who lies more during the talking stage: campus guys or campus babes?",
    "Is it socially acceptable to go on a first date at the Student Mess?",
    "A comrade texts 'Niko area, can I pull up?' What's your immediate reaction?",
    "Does posting your partner on WhatsApp status actually mean anything?",
    "What's the fastest way to get ghosted by a MMUST student?",
    "Would you rather date someone broke with good vibes or rich with zero personality?",
    "Is 'I'm focusing on my books' a valid excuse or just a polite rejection?",
    "What advice would you give to your first-year self about campus dating?",
    "What is the best (or worst) pick-up line you've heard on campus?",
    "Have you ever shot your shot in a class WhatsApp group? How did it go?",
    "Which hostel area has the most drama: Kefinco, Lurambi, or Sichirayi?",
    "What's the best street food you can get for under 100 bob around campus?",
    "HELB just dropped. What is your first irresponsible purchase?",
    "Rate your cooking skills on a scale of 'Indomie everyday' to 'Masterchef'.",
    "What's the most useless item you brought to campus in first year?",
    "What is your ultimate survival hack for the last two weeks of the semester?",
    "Kakamega rain just ruined your date plans. What's the backup plan?",
    "What's the longest you've survived on a 50 KSH budget?",
    "What is the one meal that truly defines the MMUST comrade experience?",
    "If we checked your M-Pesa statements right now, what's your most common expense?",
    "What's the ultimate 'I am a first-year' giveaway behavior?",
    "What is the unwritten rule of surviving morning classes during Kakamega's cold season?",
    "Which course at MMUST do you think has the most stylish students?",
    "What is the ultimate heartbreak song for a comrade?",
    "Best spot in Kakamega to take photos for the gram?",
    "What's the one thing you must pack when going for a sleepover at a comrade's place?",
    "Which is the most peaceful residential area for students in Kakamega?",
    "What's a major dealbreaker when someone is visiting your room for the first time?",
    "If your university life was a movie, what would the title be?",
    "If you could instantly graduate tomorrow but never see your campus friends again, would you?",
    "What is the most chaotic thing that has happened during a group discussion?",
    "What's the most annoying habit roommates have?",
    "Are you team 'study till dawn' or team 'sleep and guess in the exam'?",
    "Which joint plays the best music in Kakamega on a Friday night?",
    "What's the funniest thing you've witnessed at the Graduation Square?",
    "Have you ever accidentally texted the wrong person something embarrassing? Spill.",
    "What's the biggest lie a MMUST comrade has ever told you?",

    # --- NEW: Roommate & Hostel Drama (51 - 80) ---
    "What is the universal sign that your roommate has brought someone over?",
    "Is it a crime to cook fish in a shared hostel?",
    "What's the maximum number of days a visitor should stay in your room?",
    "Have you ever pretended to be asleep so your roommate's guest would leave?",
    "What's the most annoying thing to 'borrow' in a hostel setting?",
    "If your room could talk, what's the first secret it would spill?",
    "Worst experience with a Kakamega landlord?",
    "What is the ultimate revenge for a roommate who steals your food?",
    "Do you prefer living alone or having a roommate? Why?",
    "What is the most ridiculous rule your hostel caretaker has tried to enforce?",
    "Washing dishes immediately or leaving them 'to soak' for 3 days?",
    "What's your strategy when your roommate's alarm rings but they don't wake up?",
    "Have you ever been locked out of your room by a roommate? How did you survive?",
    "What's the most chaotic meal you've ever cooked using only a coil or heater?",
    "If someone uses your iron box without asking, what's the verdict?",
    "Is it acceptable to play loud Gengetone at 6 AM on a Saturday?",
    "What's the worst pest in campus hostels: bedbugs, roaches, or mosquitoes?",
    "Who is the most annoying person in your hostel WhatsApp group?",
    "What's the protocol when the electricity token beeps at 2 AM?",
    "What is the biggest red flag when touring a new hostel to rent?",
    "Have you ever had to fetch water from the river/borehole? Describe the trauma.",
    "What's the most embarrassing thing you've dropped while doing laundry?",
    "What is the funniest WiFi network name you've seen around campus?",
    "Have you ever had a noise complaint filed against your room?",
    "What's the golden rule of using a shared bathroom?",
    "If you find someone sitting on your bed with outside clothes, what do you do?",
    "What's the longest you've gone without electricity in Kakamega?",
    "Have you ever been forced to share a single bed with three comrades?",
    "What's the worst excuse a roommate gave for not paying their half of the rent?",
    "If someone borrows your charger and returns it broken, how do they compensate?",

    # --- NEW: Academic Survival & Campus Life (81 - 120) ---
    "What is the biggest lie lecturers tell first years?",
    "Have you ever attended a class just to sign the attendance sheet?",
    "What's the best excuse for missing a CAT that actually worked?",
    "Who suffers more: Engineering students, Med students, or IT students?",
    "What's your worst 'Missing Mark' experience?",
    "What goes through your mind when the invigilator stands right next to your desk?",
    "Have you ever done a group assignment 100% by yourself?",
    "What's the standard penalty for a group member who contributes absolutely nothing?",
    "Is sitting at the front of the lecture hall a green flag or a red flag?",
    "What's the most creative way you've seen someone cheat in an exam?",
    "Be honest, do you know your student portal password right now?",
    "What is the worst time to have a lecture scheduled?",
    "Have you ever accidentally called a lecturer 'Dad' or 'Mom'?",
    "What is the most stressful unit you've taken so far?",
    "If MMUST added a unit called 'Comrade Survival 101', what's the first topic?",
    "What's your strategy for a 3-hour lecture when your phone is at 2%?",
    "What's the weirdest thing a lecturer has ever said during a class?",
    "Have you ever defended a classmate you didn't know so they wouldn't get marked absent?",
    "What's the worst thing about using the school Wi-Fi?",
    "If you could remove one building in MMUST and replace it, what would it be?",
    "What's the most chaotic student elections memory you have?",
    "Have you ever fallen asleep in the library and woken up not knowing what year it is?",
    "What is the most elite hiding spot on campus during a strike?",
    "Who is the most powerful person on campus: The VC, the Chef, or the Security Guards?",
    "What's the most dramatic thing you've witnessed at the Administration Block?",
    "What is your go-to excuse when you haven't paid fees but want to enter the exam room?",
    "Have you ever revised for the wrong unit by mistake?",
    "What is the ultimate 'premium tears' moment academically?",
    "If your transcript was leaked to your family WhatsApp group, what happens?",
    "What's the loudest you've ever cheered during a university sports match?",
    "What is the best feeling in the world as a university student?",
    "Have you ever presented a project you knew absolutely nothing about?",
    "What's the most ridiculous thing you've written in an exam just to fill the page?",
    "Is it better to graduate with a pass and peace of mind, or first class with high blood pressure?",
    "What's the golden rule of interacting with class reps?",
    "Have you ever been kicked out of a lecture hall? Why?",
    "If you could magically master one course at MMUST without studying, what is it?",
    "What is the weirdest item you've seen someone bring to an exam room?",
    "What's the most stressful part of clearing for graduation?",
    "Have you ever printed a 50-page assignment 5 minutes before the deadline?",

    # --- NEW: Finances, HELB & Survival Hacks (121 - 150) ---
    "What is the fastest way to blow 5k in Kakamega?",
    "What is the most elite 'broke comrade' meal?",
    "If HELB was cancelled forever, how many students would actually graduate?",
    "What's the biggest financial lie you've told your parents?",
    "Omena or Ugali Mayai for the rest of the semester?",
    "What's the most embarrassing thing you've done to save money on campus?",
    "Is 'Fuliza' a comrade's best friend or worst enemy?",
    "What is the standard price for a decent haircut/salon visit around campus?",
    "If you find 1000 KSH on the ground outside MCU, what are you doing with it?",
    "What's the most expensive mistake you've made as a student?",
    "What is the unwritten rule of borrowing money from a comrade?",
    "Have you ever walked from town to campus just to save 50 bob?",
    "What's the best side hustle for a student in Kakamega?",
    "If your bank account balance was your exam score, did you pass or fail?",
    "What's the one thing you refuse to buy cheap, even when broke?",
    "How many days can a comrade realistically survive on 200 KSH?",
    "What's the most painful text to receive: 'Insufficient Funds' or 'We need to talk'?",
    "Have you ever attended an event purely for the free food?",
    "What's the best financial advice you've learned the hard way?",
    "Is betting a valid investment strategy for a comrade?",
    "What's the most ridiculous thing you've bought immediately after HELB dropped?",
    "What is the universal 'I am broke' meal combination?",
    "If someone owes you 100 bob, do you ask for it back or let it go?",
    "What is the biggest scam you fell for as a first year?",
    "Have you ever bought clothes from 'mitumba' and claimed they were from a boutique?",
    "What is the most overpriced item sold inside the school compound?",
    "If a comrade says 'I'll refund you tomorrow', what day is tomorrow?",
    "What is your ultimate tip for surviving the January semester?",
    "Have you ever negotiated a boda boda fare down to 20 bob?",
    "What's the most desperate 'send me something small' text you've drafted?",

    # --- NEW: Modern Dating, Talking Stages & Hot Takes (151 - 200) ---
    "Is it mandatory to match outfits with your partner on campus?",
    "What is the correct response when your ex says 'I miss you' during exam week?",
    "Is viewing someone's Instagram story in under 2 minutes a red flag?",
    "What's the most dramatic breakup you've witnessed in a hostel?",
    "If they take 12 hours to reply but watch your WhatsApp status, what's the diagnosis?",
    "Is 'we are just friends' the biggest lie told on campus?",
    "What is the ultimate sign of 'Character Development'?",
    "Would you forgive someone who dumped you but later sent you 5k?",
    "What's the most petty reason you stopped talking to someone?",
    "Is it a flex to have your partner's face as your wallpaper?",
    "What is the unspoken rule about dating your roommate's friend?",
    "Have you ever been taken on a 'walking date' around Kakamega forest?",
    "What does it mean if they only text you after 10 PM?",
    "If they refuse to post you on their birthday, are you single?",
    "What's the most ridiculous standard people have for dating on campus?",
    "Is 'let's go study together' a date or a trap to make you do their assignment?",
    "Have you ever fought over a comrade? Was it worth it?",
    "What's the standard mourning period for a 2-week talking stage?",
    "Is blocking someone a sign of immaturity or peace of mind?",
    "What's the most elite response to 'You're too good for me'?",
    "If you find out your campus crush doesn't know how to cook, is it a dealbreaker?",
    "Have you ever stayed in a toxic relationship just because they had Wi-Fi?",
    "What's the most suspicious name someone can save you as on their phone?",
    "Is going to the cinema in town considered a high-end date?",
    "What's the worst advice your friends have given you about your relationship?",
    "If a comrade asks 'Are you single?' what is the safest answer?",
    "Have you ever been the 'villain' in someone's campus story?",
    "What's the boldest way someone has ever asked for your number?",
    "Is it acceptable to date someone from a rival university?",
    "What's the ultimate 'I want to be more than friends' signal?",
    "Have you ever pretended to like a specific music genre just to impress a crush?",
    "What is the maximum acceptable age gap for dating in university?",
    "Is sharing passwords true love or a privacy violation?",
    "What's the funniest lie you've used to escape a bad date?",
    "If your current relationship status was a weather forecast, what is it?",
    "What is the most brutal way to friendzone someone?",
    "Have you ever crushed on a lecturer? (We won't judge).",
    "What's the worst place to get into an argument with your partner on campus?",
    "If they say 'I don't want a label right now', what are you doing?",
    "What is the unwritten rule of dating someone in the same discussion group?",
    "Is taking someone to a campus event a valid first date?",
    "What's the most elite response to getting rejected?",
    "Have you ever matched with someone on a dating app and then seen them in class?",
    "What's the biggest green flag a comrade can have on their social media profile?",
    "If they ask 'What are we?', what is the most terrifying answer?",
    "What's the most overused pickup line by Kakamega guys?",
    "Is 'I lost my phone' a valid excuse for ignoring someone for a week?",
    "What's the most iconic way to announce you are officially single?",
    "If you could ban one phrase from campus dating vocabulary, what would it be?",
    "What's the ultimate secret to surviving MMUST Dating AI?"
]
def get_todays_prompt():
    """Lazy evaluator: Checks if today has a prompt. If not, sets one."""
    today_str = datetime.now(EAT).strftime('%Y-%m-%d')
    prompt_ref = db.reference(f'daily_prompts/{today_str}')
    prompt_data = prompt_ref.get()

    if not prompt_data:
        # It's a new day! Pick a random prompt.
        question = random.choice(CAMPUS_PROMPTS)
        prompt_data = {'question': question, 'date': today_str}
        prompt_ref.set(prompt_data)
        
    return prompt_data

@app.route('/feed')
@requires_subscription
def campus_feed():
    """Renders the Daily Icebreaker Feed"""
    user_id = session.get('user_id')
    today_str = datetime.now(EAT).strftime('%Y-%m-%d')
    
    prompt_data = get_todays_prompt()
    question = prompt_data.get('question')
    
    # Check if current user has answered today's prompt
    my_answer_data = db.reference(f'prompt_answers/{today_str}/{user_id}').get()
    has_answered = bool(my_answer_data)
    
    feed_answers = []
    
    if has_answered:
        # User has answered, fetch everyone else's answers!
        all_answers = db.reference(f'prompt_answers/{today_str}').get() or {}
        profiles = db.reference('profiles').get() or {}
        
        for uid, ans_data in all_answers.items():
            if uid != user_id: # Don't show the user their own answer in the feed
                user_profile = profiles.get(uid, {})
                
                # Only show answers from users who are visible
                if user_profile.get('is_visible', True):
                    feed_answers.append({
                        'user_id': uid,
                        'name': user_profile.get('name', 'Student').split(' ')[0],
                        'img': user_profile.get('img', '/static/img/placeholder.png'),
                        'answer': ans_data.get('answer'),
                        'timestamp': ans_data.get('timestamp')
                    })
        
        # Sort answers by newest first
        feed_answers.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
    return render_template('feed.html', 
                           question=question, 
                           has_answered=has_answered, 
                           my_answer=my_answer_data.get('answer') if my_answer_data else "",
                           answers=feed_answers)

@app.route('/api/answer_prompt', methods=['POST'])
def answer_prompt():
    """Saves the user's answer to Firebase"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
        
    data = request.json
    answer = data.get('answer')
    
    if not answer or len(answer.strip()) < 2:
        return jsonify({'success': False, 'message': 'Your answer is too short!'})
        
    today_str = datetime.now(EAT).strftime('%Y-%m-%d')
    
    db.reference(f'prompt_answers/{today_str}/{user_id}').set({
        'answer': answer.strip(),
        'timestamp': datetime.now(EAT).isoformat()
    })
    
    return jsonify({'success': True})   
    
    
# ==========================================
# THE SECRET ADMIRER ENGINE (CURIOSITY LOOP)
# ==========================================
@app.route('/secret-admirer')
@requires_subscription
def secret_admirer():
    """Renders the Secret Admirer Page"""
    user_id = session.get('user_id')
    
    # Fetch the current user's profile to know their gender
    user_profile = db.reference(f'profiles/{user_id}').get() or {}
    current_user_gender = user_profile.get('gender', '').strip().lower()
    
    # 1. Count how many people are secretly crushing on this user
    my_admirers = db.reference(f'secret_crushes/{user_id}').get() or {}
    
    # 2. Get the list of people THIS user has crushed on (so they can track them)
    all_crushes = db.reference('secret_crushes').get() or {}
    my_crushes = []
    
    # Optional: Fetch all profiles once if you want to strictly filter the admirer count by gender too,
    # but since we are blocking it at the API level below, trusting the DB count is fine here.
    admirer_count = len([k for k, v in my_admirers.items() if v.get('status') == 'pending'])
    
    for target_id, senders in all_crushes.items():
        if user_id in senders:
            target_profile = db.reference(f'profiles/{target_id}').get()
            if target_profile:
                my_crushes.append({
                    'name': target_profile.get('name', 'Student').split(' ')[0],
                    'img': target_profile.get('img', '/static/img/placeholder.png'),
                    'status': senders[user_id].get('status', 'pending')
                })

    return render_template('crush.html', admirer_count=admirer_count, my_crushes=my_crushes)


@app.route('/api/submit_crush', methods=['POST'])
def submit_crush():
    """Handles the logic of sending a crush and checking for mutual matches"""
    sender_id = session.get('user_id')
    if not sender_id:
        return jsonify({'success': False, 'message': 'Session expired. Please log in.'}), 401

    data = request.json
    target_reg_raw = data.get('target_reg', '').strip().upper()
    target_id = target_reg_raw.replace('/', '_') # Standardize ID format

    if sender_id == target_id:
        return jsonify({'success': False, 'message': "You can't crush on yourself! 😂"})

    # Fetch both profiles to check gender and existence
    sender_profile = db.reference(f'profiles/{sender_id}').get() or {}
    target_profile = db.reference(f'profiles/{target_id}').get()

    if not target_profile:
        return jsonify({'success': False, 'message': "We couldn't find a student with that Registration Number on the app."})

    # --- STRICT OPPOSITE-GENDER RULE ---
    sender_gender = sender_profile.get('gender', '').strip().lower()
    target_gender = target_profile.get('gender', '').strip().lower()

    if not sender_gender or not target_gender:
        return jsonify({'success': False, 'message': "Both users must have their gender set to use the Secret Admirer feature."})

    if sender_gender == target_gender:
        return jsonify({'success': False, 'message': "System Rule: You can only send a Secret Crush to someone of the opposite gender."})

    # CHECK FOR MUTUAL MATCH (Did they already crush on the sender?)
    target_crushes_on_me = db.reference(f'secret_crushes/{sender_id}/{target_id}').get()

    now_eat = datetime.now(EAT).isoformat()

    if target_crushes_on_me:
        # ❤️ IT IS A MUTUAL MATCH! ❤️
        # 1. Upgrade the crush status
        db.reference(f'secret_crushes/{target_id}/{sender_id}').set({'timestamp': now_eat, 'status': 'matched'})
        db.reference(f'secret_crushes/{sender_id}/{target_id}').update({'status': 'matched'})

        # 2. Create an official Chat Match in the database
        match_id = f"match_{min(sender_id, target_id)}_{max(sender_id, target_id)}"
        db.reference(f'matches/{match_id}').set({
            'users': {sender_id: True, target_id: True},
            'timestamp': now_eat,
            'is_perfect_match': True,
            'type': 'secret_crush'
        })
        
        # 3. Fire Push Notification to the target
        # TODO: Implement send_push_notification(target_id, "OMG! It's a mutual crush! You've been matched! ❤️")

        return jsonify({
            'success': True, 
            'mutual': True, 
            'message': "OMG! They had a crush on you too! ❤️ We just created a match in your chats."
        })

    else:
        # 🤫 NOT MUTUAL YET (Anonymous Mode)
        db.reference(f'secret_crushes/{target_id}/{sender_id}').set({
            'timestamp': now_eat,
            'status': 'pending'
        })
        
        # 3. Fire Push Notification to the target
        # TODO: Implement send_push_notification(target_id, "Someone has a Secret Crush on you! 👀 Open the app to see.")

        return jsonify({
            'success': True, 
            'mutual': False, 
            'message': "Secret Crush sent! 🤫 If they enter your Reg Number too, you will instantly match."
        })
        
import os
import random
import logging
from flask import request, jsonify, render_template, session, url_for
from twilio.rest import Client
from flask_socketio import emit, join_room, leave_room

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
#  1. DEDICATED CALL PAGE ROUTE
# ─────────────────────────────────────────────────────────────
@app.route('/call/<partner_id>')
@requires_subscription
def call_page(partner_id):
    # Determine if they are initiating or answering based on URL parameters
    action = request.args.get('action', 'call') # 'call' or 'answer'
    is_video = request.args.get('video', 'false') == 'true'
    
    # Fetch partner data safely
    try:
        partner_data = db.reference(f'profiles/{partner_id}').get() or {}
        partner_name = partner_data.get('name', 'Student').split()[0]
        partner_img = partner_data.get('img', '/static/img/placeholder.png')
    except Exception as e:
        logger.error(f"Error fetching partner data for call: {e}")
        partner_name = "Student"
        partner_img = '/static/img/placeholder.png'

    return render_template('call.html', 
                           partner_id=partner_id,
                           partner_name=partner_name,
                           partner_img=partner_img,
                           action=action,
                           is_video=is_video)


# ─────────────────────────────────────────────────────────────
#  2. TWILIO TURN CREDENTIALS (E2EE Firewall Bypass)
# ─────────────────────────────────────────────────────────────
@app.route('/api/turn-credentials')
@requires_subscription
def get_turn_credentials():
    """Generates temporary, secure tokens to punch through strict university firewalls."""
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    
    if not account_sid or not auth_token:
        logger.error("Missing Twilio credentials in environment.")
        return jsonify({'error': 'Server config error'}), 500

    try:
        client = Client(account_sid, auth_token)
        token = client.tokens.create()
        return jsonify({'iceServers': token.ice_servers})
    except Exception as e:
        logger.error(f"Twilio Token Generation Error: {e}")
        return jsonify({'error': 'Failed to generate network routing'}), 500


# ─────────────────────────────────────────────────────────────
#  3. WEBRTC SIGNALING & E2EE HANDSHAKE (Socket.IO)
# ─────────────────────────────────────────────────────────────
@socketio.on('join_call_room')
def on_join_call_room(data):
    """Users join a private room matching their ID to receive direct signals."""
    user_id = data.get('user_id')
    if user_id:
        join_room(user_id)

# Step A: Caller invites Receiver (Rings their phone globally)
@socketio.on('call_invite')
def handle_call_invite(data):
    target_id = data.get('target_id')
    if target_id:
        emit('incoming_call', data, room=target_id)

# Step B: Receiver accepts, loads the page, and tells Caller they are ready
@socketio.on('receiver_ready')
def handle_receiver_ready(data):
    caller_id = data.get('caller_id')
    if caller_id:
        emit('receiver_ready', data, room=caller_id)

# Step C: Caller generates WebRTC Offer and sends it securely
@socketio.on('webrtc_offer')
def handle_offer(data):
    target_id = data.get('target_id')
    if target_id:
        emit('webrtc_offer', data, room=target_id)

# Step D: Receiver generates WebRTC Answer and sends it back
@socketio.on('webrtc_answer')
def handle_answer(data):
    caller_id = data.get('caller_id')
    if caller_id:
        emit('call_answered', data, room=caller_id)

# Step E: Connect the audio/video streams (ICE Candidates)
@socketio.on('webrtc_ice_candidate')
def handle_ice_candidate(data):
    target_id = data.get('target_id')
    if target_id:
        emit('new_ice_candidate', data, room=target_id)

# Step F: End Call
@socketio.on('end_call')
def handle_end_call(data):
    target_id = data.get('target_id')
    if target_id:
        emit('call_ended', room=target_id)

# ─────────────────────────────────────────────────────────────
#  4. LIVE TALK DIRECTORY
# ─────────────────────────────────────────────────────────────
@app.route('/talk')
@requires_subscription
def talk_directory():
    """Displays all currently online, visible, and paid users for live calling."""
    user_id = session.get('user_id')
    
    try:
        all_profiles = db.reference('profiles').get() or {}
    except Exception as e:
        logger.error('talk_directory: Firebase read failed: %s', e)
        all_profiles = {}

    # 1. Fetch the current user's gender to compare against others
    current_user_profile = all_profiles.get(user_id, {})
    current_user_gender = current_user_profile.get('gender', '').strip().lower()

    online_users = []

    for p_id, p in all_profiles.items():
        if not isinstance(p, dict):
            continue
            
        # Exclude self, offline users, free users, and hidden users
        if (p_id == user_id or 
            not p.get('is_online') or 
            p.get('is_paid') != True or 
            not p.get('is_visible', True)):
            continue

        # 2. Get the partner's gender
        partner_gender = p.get('gender', '').strip().lower()
        
        # Generate the random AI score (or fetch if it exists)
        ai_score = p.get('ai_score', random.randint(60, 95))

        # 3. Restrict "Perfect Match" functionality between same-gender profiles
        is_opposite_gender = bool(current_user_gender and partner_gender and current_user_gender != partner_gender)
        
        is_perfect_match = False
        if is_opposite_gender and ai_score >= 80:
            is_perfect_match = True

        # 4. Determine unread messages from this specific partner
        unread_count = 0
        match_id = f"match_{min(user_id, p_id)}_{max(user_id, p_id)}"
        chat_data = db.reference(f'matches/{match_id}/messages').get() or {}
        
        for msg_id, msg in chat_data.items():
            if msg.get('sender_id') == p_id and msg.get('status') != 'read':
                unread_count += 1

        online_users.append({
            'id': p_id,
            'name': p.get('name', 'Student').split()[0],
            'img': p.get('img') or url_for('static', filename='img/placeholder.png'),
            'course': p.get('course', 'MMUST Student'),
            'is_perfect_match': is_perfect_match,
            'unread_count': unread_count
        })

    # Sort: Perfect matches float to the top, then alphabetically
    online_users.sort(key=lambda u: (not u['is_perfect_match'], u['name']))

    return render_template('talk.html', online_users=online_users)


@app.route('/call-review/<partner_id>')
@requires_subscription
def call_review(partner_id):
    """Loads the post-call vibe check and quality rating screen."""
    try:
        partner_data = db.reference(f'profiles/{partner_id}').get() or {}
        partner_name = partner_data.get('name', 'Student').split()[0]
        partner_img = partner_data.get('img', '/static/img/placeholder.png')
    except Exception as e:
        logger.error(f"Error fetching partner data for review: {e}")
        partner_name = "Student"
        partner_img = '/static/img/placeholder.png'

    return render_template('call_review.html',
                           partner_id=partner_id,
                           partner_name=partner_name,
                           partner_img=partner_img)


@app.route('/api/submit-review', methods=['POST'])
@requires_subscription
def submit_review():
    """Processes the call feedback and handles safety reporting."""
    user_id = session.get('user_id')
    data = request.json

    partner_id = data.get('partner_id')
    vibe = data.get('vibe')         # 'up' or 'down'
    quality = data.get('quality')   # 1 to 5
    report = data.get('report', False)

    try:
        # Save the review data
        db.reference(f'call_reviews/{user_id}/{partner_id}').set({
            'vibe': vibe,
            'quality': quality,
            'reported': report,
            'timestamp': datetime.now(EAT).isoformat()
        })

        # Check if the partner also gave a thumbs up (Mutual Vibe Match)
        partner_review = db.reference(f'call_reviews/{partner_id}/{user_id}').get()
        mutual_match = False
        
        # Standard matching is allowed for all users after a successful call
        if partner_review and partner_review.get('vibe') == 'up' and vibe == 'up':
            mutual_match = True
            # Unlock further messaging or set a mutual vibe flag here
            db.reference(f'matches/{user_id}/{partner_id}').set(True)
            db.reference(f'matches/{partner_id}/{user_id}').set(True)

        # Process safety report
        if report:
            db.reference('admin_alerts').push({
                'sender': user_id,
                'reported_user': partner_id,
                'flag': 'call_report',
                'message': 'User flagged inappropriate behavior or content during a live WebRTC call.',
                'timestamp': datetime.now(EAT).isoformat()
            })

        return jsonify({'success': True, 'mutual_match': mutual_match})
    
    except Exception as e:
        logger.error(f"Failed to submit call review: {e}")
        return jsonify({'success': False, 'message': 'Database error'}), 500
     

# Relay in-call emoji reactions
@socketio.on('call_reaction')
def handle_call_reaction(data):
    target_id = data.get('target_id')
    if target_id:
        emit('receive_reaction', {'emoji': data.get('emoji')}, room=target_id)


@app.route('/api/online_count')
def online_count():
    """Optimized API to fetch the total number of online users."""
    try:
        # Ask Firebase to ONLY send profiles where is_online is True.
        # Because the index was added, Firebase does this instantly.
        online_profiles = db.reference('profiles').order_by_child('is_online').equal_to(True).get()
        
        if online_profiles:
            count = len(online_profiles)
        else:
            count = 0
            
        # Optional: Add a baseline so the application never looks empty
        display_count = count if count > 0 else 1 
        
        return jsonify({'count': display_count})
    except Exception as e:
        logger.error(f"Failed to fetch online count: {e}")
        return jsonify({'count': 1})

           
import math

import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate the distance between two points on Earth using the Haversine formula."""
    if not all([lat1, lon1, lat2, lon2]):
        return -1 # Use -1 to indicate an invalid or missing distance
        
    try:
        R = 6371  # Radius of the Earth in km
        dlat = math.radians(float(lat2) - float(lat1))
        dlon = math.radians(float(lon2) - float(lon1))
        
        a = math.sin(dlat/2) * math.sin(dlat/2) + math.cos(math.radians(float(lat1))) \
            * math.cos(math.radians(float(lat2))) * math.sin(dlon/2) * math.sin(dlon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        d = R * c
        return d
    except (ValueError, TypeError):
        return -1

@app.route('/directory')
@requires_subscription
def full_directory():
    """Shows all available users, their online status, and unread chat counts."""
    user_id = session.get('user_id')
    search_query = request.args.get('q', '').strip().lower()
    
    all_profiles = db.reference('profiles').get() or {}
    current_user_profile = all_profiles.get(user_id, {})
    
    # Get current user's location for distance calculation
    current_user_location = current_user_profile.get('location', {})
    my_lat = current_user_location.get('latitude')
    my_lon = current_user_location.get('longitude')
    
    # Fetch all matches to identify mutual connections
    all_matches = db.reference('matches').get() or {}
    my_mutual_matches = []
    for match_id, m_data in all_matches.items():
        if user_id in m_data.get('users', {}):
             users_dict = m_data.get('users', {})
             other_id = next((uid for uid in users_dict.keys() if uid != user_id), None)
             if other_id:
                 my_mutual_matches.append(other_id)

    directory_users = []
    
    for p_id, p in all_profiles.items():
        if not isinstance(p, dict) or p_id == user_id or not p.get('is_visible', True):
            continue
            
        partner_name = p.get('name', 'Student')
        
        # Search Filter
        if search_query and search_query not in partner_name.lower():
            continue
            
        # Calculate unread messages from this specific user
        unread_count = 0
        match_id = f"match_{min(user_id, p_id)}_{max(user_id, p_id)}"
        chat_data = db.reference(f'matches/{match_id}/messages').get() or {}
        
        for msg_id, msg in chat_data.items():
            deleted_for = msg.get('deleted_for', [])
            if msg.get('sender_id') == p_id and msg.get('status') != 'read' and user_id not in deleted_for:
                unread_count += 1

        # Check Mutual Match
        is_mutual = p_id in my_mutual_matches
        
        # Calculate Distance
        partner_location = p.get('location', {})
        p_lat = partner_location.get('latitude')
        p_lon = partner_location.get('longitude')
        distance = calculate_distance(my_lat, my_lon, p_lat, p_lon)
        
        # For sorting purposes, if distance is -1, treat it as very far away
        sort_distance = distance if distance != -1 else 999999

        directory_users.append({
            'id': p_id,
            'name': partner_name.split()[0],
            'full_name': partner_name,
            'img': p.get('img') or '/static/img/placeholder.png',
            'course': p.get('course', 'MMUST Student'),
            'is_online': p.get('is_online', False),
            'unread_count': unread_count,
            'is_mutual': is_mutual,
            'distance': distance,
            'sort_distance': sort_distance,
            'last_online': p.get('last_online', '1970-01-01T00:00:00') 
        })

    # Sort Logic:
    directory_users.sort(key=lambda u: (
        -u['unread_count'], 
        not u['is_online'], 
        not u['is_mutual'],
        u['sort_distance'],
        u['last_online']
    ), reverse=False)

    return render_template('directory.html', directory_users=directory_users, search_query=search_query)   
import uuid
from flask_socketio import join_room, leave_room, emit
from datetime import datetime
import pytz

# ==========================================
# 🔦 FRIDAY NIGHT "LIGHTS OUT" ENGINE
# ==========================================

# Temporary in-memory queue for matchmaking
lights_out_queue = {
    'male': [],
    'female': []
}

@app.route('/lights-out')
@requires_subscription
def lights_out():
    """Renders the Lights Out lobby."""
    # Optional: You can enforce the Friday 9 PM rule here.
    # eat_tz = pytz.timezone('Africa/Nairobi')
    # now = datetime.now(eat_tz)
    # if now.weekday() != 4 or not (21 <= now.hour < 22):
    #     flash("Lights Out is only active on Fridays between 9 PM and 10 PM!", "warning")
    #     return redirect(url_for('dashboard'))
        
    return render_template('lights_out.html')

@socketio.on('join_lights_out_queue')
def handle_join_lights_out():
    user_id = session.get('user_id')
    if not user_id:
        return

    # 1. Get user gender to enforce opposite-gender matching
    profile = db.reference(f'profiles/{user_id}').get() or {}
    gender = profile.get('gender', '').strip().lower()
    
    if gender not in ['male', 'female']:
        emit('queue_error', {'message': 'Gender must be specified in profile to join.'})
        return

    target_queue = 'female' if gender == 'male' else 'male'
    my_queue = 'male' if gender == 'male' else 'female'

    # 2. Check if there is someone in the opposite queue
    if len(lights_out_queue[target_queue]) > 0:
        # Match found!
        partner = lights_out_queue[target_queue].pop(0)
        room_id = f"lights_out_{uuid.uuid4().hex[:8]}"
        
        # Add current user to room
        join_room(room_id)
        
        # Tell both clients they matched and give them the room ID
        emit('lights_out_match_found', {'room': room_id}, room=room_id)
        emit('lights_out_match_found', {'room': room_id}, to=partner['sid'])
        
        # Add the partner to the SocketIO room as well
        # (In Flask-SocketIO, you can't easily force another SID into a room from here 
        # without client action, so we tell the partner's client to join via an event)
        emit('force_join_room', {'room': room_id}, to=partner['sid'])
    else:
        # No match yet, add to my queue
        # Ensure not already in queue
        lights_out_queue[my_queue] = [u for u in lights_out_queue[my_queue] if u['user_id'] != user_id]
        lights_out_queue[my_queue].append({'user_id': user_id, 'sid': request.sid})
        emit('waiting_in_queue')

@socketio.on('lights_out_client_join_room')
def client_join_room(data):
    """Partner client responds to force_join_room"""
    room_id = data.get('room')
    if room_id:
        join_room(room_id)

@socketio.on('send_lights_out_message')
def handle_lights_out_message(data):
    room = data.get('room')
    message = data.get('message')
    # Emit to everyone in the room EXCEPT the sender
    emit('receive_lights_out_message', {'message': message}, room=room, include_self=False)

@socketio.on('lights_out_reveal_vote')
def handle_reveal_vote(data):
    room = data.get('room')
    user_id = session.get('user_id')
    # Emit to the room that a user voted yes. The frontend will count if both voted.
    emit('partner_voted_reveal', {'user_id': user_id}, room=room, include_self=False) 
from datetime import datetime

# ==========================================
# 🤫 CAMPUS GOSSIP & MISSED CONNECTIONS
# ==========================================

@app.route('/campus-gossip')
def campus_gossip():
    """
    Renders the anonymous gossip feed, sorting newest posts first.
    """
    user_id = session.get('user_id')
    if not user_id:
        # Allow logged out users to see the page but with "blurred" content 
        # actually we handle that in the template logic or here.
        # For now, let's allow viewing the feed but with restricted interactions.
        pass
        
    # Fetch the last 50 posts from Firebase
    gossip_ref = db.reference('missed_connections').order_by_child('timestamp').limit_to_last(50).get() or {}
    
    posts = []
    for post_id, data in gossip_ref.items():
        data['id'] = post_id
        posts.append(data)
        
    # Sort posts newest first
    posts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    
    current_user_name = session.get('user_name', 'Guest')
    
    return render_template('gossip.html', posts=posts, current_user={'name': current_user_name})

@app.route('/gossip/<post_id>')
def view_gossip_post(post_id):
    """Publicly accessible link for a specific gossip post."""
    post = db.reference(f'missed_connections/{post_id}').get()
    if not post:
        return "Gossip post not found.", 404
        
    post['id'] = post_id
    user_id = session.get('user_id')
    
    # If not logged in, we'll show a "Join to read more" version in the template
    is_logged_in = bool(user_id)
    
    return render_template('gossip.html', posts=[post], single_post=True, is_logged_in=is_logged_in)

@app.route('/api/post_gossip', methods=['POST'])
def post_gossip():
    """Saves an anonymous post to the database."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
        
    data = request.json
    text = data.get('text', '').strip()
    
    if not text or len(text) < 10:
        return jsonify({'success': False, 'message': 'Your confession is too short!'}), 400
        
    db.reference('missed_connections').push({
        'text': text,
        'author_id': user_id, 
        'timestamp': datetime.now().isoformat(),
        'upvotes': 0,
        'comments': {}
    })
    
    return jsonify({'success': True, 'message': 'Confession posted anonymously!'})

@app.route('/api/upvote_gossip/<post_id>', methods=['POST'])
def upvote_gossip(post_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Log in to upvote'}), 401
        
    post_ref = db.reference(f'missed_connections/{post_id}')
    post = post_ref.get()
    if not post:
        return jsonify({'success': False, 'message': 'Post not found'}), 404
        
    current_upvotes = post.get('upvotes', 0)
    post_ref.update({'upvotes': current_upvotes + 1})
    return jsonify({'success': True})

@app.route('/api/comment_gossip/<post_id>', methods=['POST'])
def comment_gossip(post_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'message': 'Log in to comment'}), 401
        
    data = request.json
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'Comment cannot be empty'}), 400
        
    db.reference(f'missed_connections/{post_id}/comments').push({
        'text': text,
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id # still stored for moderation but hidden in UI
    })
    return jsonify({'success': True})
   
import os
from groq import Groq
from flask import request, jsonify, session

# Initialize Groq Client (Make sure GROQ_API_KEY is in your .env file)
groq_client = Groq(api_key=os.getenv('GROQ_API_KEY'))

@app.route('/api/wingman/execute', methods=['POST'])
def api_wingman_execute():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Log in required.'}), 401
        
    data = request.json
    action = data.get('action')
    
    if action not in ['roast', 'icebreaker']:
        return jsonify({'success': False, 'message': 'Invalid action.'}), 400

    try:
        # 1. Fetch user's profile data
        user_id = session['user_id']
        user_data = db.reference(f'profiles/{user_id}').get() or {}
        
        bio = user_data.get('bio', 'No bio provided.')
        interests = ", ".join(user_data.get('interests', ['Nothing specific']))
        course = user_data.get('course', 'Unknown Course')
        
        # 2. Construct the AI Prompt
        if action == 'roast':
            system_prompt = "You are a savage, funny, but ultimately helpful dating coach. Your goal is to roast the user's dating profile and tell them how to fix it. Keep it under 150 words."
            user_prompt = f"Roast my dating profile: I am a university student studying {course}. My bio is: '{bio}'. My interests are: {interests}."
        elif action == 'icebreaker':
            system_prompt = "You are a master at flirting and smooth conversation starters. Provide exactly 3 highly creative, witty, and unique icebreakers the user can send to their matches. Format them clearly with numbers."
            user_prompt = f"I need 3 icebreakers. My personality/interests involve: {interests}. I study {course}."

        # 3. Call Groq API (Using LLaMA-3 or Mixtral for speed)
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="llama3-8b-8192", # Groq's extremely fast model
            temperature=0.8,
            max_tokens=300,
        )
        
        ai_response = chat_completion.choices[0].message.content
        
        return jsonify({'success': True, 'response': ai_response})
        
    except Exception as e:
        logger.error(f"Groq Wingman Error: {e}")
        return jsonify({'success': False, 'message': 'The AI engine is currently overloaded. Try again in a moment.'}), 500    
if __name__ == '__main__':
    # Grab the port from Render's environment, default to 5000 for local testing
    port = int(os.environ.get('PORT', 5000))
    # You must listen on '0.0.0.0' for external traffic on a server!
    socketio.run(app, host='0.0.0.0', port=port, debug=False)