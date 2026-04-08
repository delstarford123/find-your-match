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

from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room
from pywebpush import webpush, WebPushException
from groq import Groq

# ==========================================
# 1. PATH SETUP & ENVIRONMENT
# ==========================================
load_dotenv()
# 👇 This line tells Python where to find the 'app' folder
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
from app.email_service import send_date_approval_email

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

# VAPID Keys for Push Notifications
# Using os.getenv so your personal email isn't hardcoded if you share the code
mail_username = os.getenv("MAIL_USERNAME", "delstarfordisaiah@gmail.com")
app.config['VAPID_PRIVATE_KEY'] = "private_key.pem" 
app.config['VAPID_CLAIMS'] = {"sub": f"mailto:{mail_username}"}

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

    # 3. Bundle Context for the Frontend
    current_user = {
        'id': user_id,
        'name': user_profile.get('name', session.get('user_name', 'Student')).split(' ')[0], 
        'img': user_profile.get('img') or url_for('static', filename='img/placeholder.png'),
        'settings': user_profile.get('settings', {}) 
    }

    # 4. Build the Discovery Deck
    potential_matches = []
    all_profiles = get_all_profiles() # Fetch everyone
    
    for p in all_profiles:
        p_id = p.get('id')
        
        # SKIP CONDITIONS:
        # - Don't show the user themselves
        # - Don't show profiles that are hidden
        # - Don't show people the user has already swiped on (liked/passed)
        if p_id == user_id or not p.get('is_visible', True) or p_id in user_swipes:
            continue
            
        # Retrieve AI score safely, default to a random high score if not calculated yet
        ai_score = p.get('ai_score', random.randint(65, 95))
        
        potential_matches.append({
            'id': p_id,
            'name': p.get('name', 'Student').split(' ')[0],
            'age': p.get('age', 18),
            'major': p.get('major', 'MMUST Student'),
            'bio': p.get('bio', 'Hey! I am using MMUST Dating AI.'),
            'img': p.get('img') or url_for('static', filename='img/placeholder.png'),
            'compatibility': ai_score,
            'is_perfect_match': ai_score >= 80  # Flag for the frontend badge
        })

    # 5. Sort the deck: Show the Highest Compatibility matches first!
    potential_matches.sort(key=lambda x: x['compatibility'], reverse=True)

    return render_template(
        'swipe.html', 
        current_user=current_user,
        potential_matches=potential_matches
    )
import random

@app.route('/dashboard')
@requires_subscription
def dashboard():
    """THE MAIN STUDENT COMMAND CENTER (OPEN DIRECTORY MODE)"""
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
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
                
            # Skip the user themselves and hidden profiles
            if p_id != user_id and p.get('is_visible', True):
                # Fetch or simulate compatibility score
                ai_score = p.get('ai_score', random.randint(65, 95))
                
                my_matches.append({
                    'id': p_id,
                    'name': p.get('name', 'Student').split(' ')[0], 
                    'bio': p.get('bio', 'MMUST Student'),
                    'img': p.get('img') or url_for('static', filename='img/placeholder.png'),
                    'compatibility': ai_score,
                    'is_perfect_match': ai_score >= 80 # Triggers the ❤️ Perfect Match badge
                })
        
        # 2. Sort by highest compatibility first
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
        upcoming_dates=upcoming_dates
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
        
        # 1. FIXED: Fetch all matches and filter in Python to PREVENT Firebase crashes!
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

        # 2. Fetch ALL profiles in the system
        all_profiles = get_all_profiles()
        
        # 3. Build the inbox list with EVERYONE
        for p in all_profiles:
            # Skip the current user themselves and hidden profiles
            if p['id'] != user_id and p.get('is_visible', True): 
                p_id = p['id']
                is_mutual = p_id in matched_data
                
                if is_mutual:
                    last_msg = matched_data[p_id]['last_message']
                    last_msg_time = matched_data[p_id]['last_message_time']
                else:
                    last_msg = 'Tap to start chatting'
                    last_msg_time = ''
                
                # Retrieve AI score safely, default to 0
                ai_score = p.get('ai_score', 0)
                
                my_matches.append({
                    'id': p_id,
                    'name': p.get('name', 'Student').split(' ')[0], # First Name only
                    'img': p.get('img', '/static/img/placeholder.png'),
                    'is_perfect_match': ai_score > 80, # ❤️ TRIGGERS PERFECT MATCH BADGE
                    'is_online': p.get('is_online', False),
                    'is_mutual_match': is_mutual,      # 🔥 TRIGGERS MUTUAL MATCH GLOW
                    'last_message': last_msg,
                    'last_message_time': last_msg_time
                })
        
        # 4. ALWAYS append the AI Wingman to the list
        my_matches.append({
            'id': 'AI_COMPANION', 'name': 'AI Wingman',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=wingman',
            'is_perfect_match': False, 'is_online': True, 'is_mutual_match': False,
            'last_message': 'Need dating advice?', 'last_message_time': ''
        })

        # 5. Sort matches (Mutual matches first, then by time)
        my_matches.sort(key=lambda x: (x['is_mutual_match'], x.get('last_message_time', '')), reverse=True)

        if not partner_id and my_matches:
            partner_id = my_matches[0]['id']

    # Find the data for the person currently being chatted with
    active_partner = next((m for m in my_matches if str(m['id']) == str(partner_id)), None)
    
    if partner_id and not active_partner and not ai_mode:
        flash("This student could not be found.", "warning")
        return redirect(url_for('matches'))

    # Load the chat history
    history = get_chat_history(user_id, partner_id) if active_partner else []
    
    return render_template('matches.html', 
                           current_user=session.get('user_name'),
                           my_matches=my_matches,
                           active_partner=active_partner,
                           chat_history=history)   
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
        
        # 🆕 Grab the new Intent Tag (defaults to 'none' if they didn't touch it)
        intent = request.form.get('intent', 'none') 

        try:
            # 2. Save filter settings to the 'settings' sub-node
            user_ref.child('settings').update({
                'looking_for': gender_pref,
                'major_filter': major_filter,
                'strict_schedule': strict_mode,
                'ai_companion_mode': ai_mode
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
        
        # 🆕 Pass the intent back so the dropdown remembers their choice
        'intent': user_profile.get('intent', 'none') 
    }

    # 3. Render the page
    return render_template(
        'settings.html', 
        current_user=session.get('user_name'),
        user=template_user_data
    )

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
# ==========================================
# GOD MODE: SUPER ADMIN DASHBOARD
# ==========================================
@app.route('/admin/super', methods=['GET', 'POST'])
def super_admin():
    # SECURITY: Never use a fallback password in production.
    ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASS")
    
    if not ADMIN_PASSWORD:
        logger.critical("SUPER_ADMIN_PASS environment variable is missing!")
        return "CRITICAL ERROR: Admin environment not configured safely.", 500

    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_super_admin'] = True
            session.permanent = False  # Forces session to expire when browser closes
            flash("Welcome to God Mode, Creator.", "success")
        else:
            logger.warning(f"Failed God Mode login attempt from IP: {request.remote_addr}")
            flash("Access Denied. Incorrect Password.", "error")
        return redirect(url_for('super_admin'))
        
    if not session.get('is_super_admin'):
        return render_template('super_admin.html', logged_in=False)

    try:
        # Fetch Core Data
        all_profiles = db.reference('profiles').get() or {}
        all_restaurants = db.reference('restaurants').get() or {}
        alerts_dict = db.reference('admin_alerts').get() or {}
        
        # Fetch Support System Data
        feedbacks_dict = db.reference('feedbacks').get() or {}
        call_requests_dict = db.reference('call_requests').get() or {}
        
        # Calculate Revenue (Safely checking if it's a dict to prevent Firebase type errors)
        student_revenue = sum(20 for p in all_profiles.values() if isinstance(p, dict) and p.get('is_paid'))
        b2b_revenue = sum(2000 for r in all_restaurants.values() if isinstance(r, dict) and r.get('subscription_active'))
        total_revenue = student_revenue + b2b_revenue

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

        return render_template('super_admin.html', 
                               logged_in=True,
                               total_revenue=total_revenue,
                               student_revenue=student_revenue,
                               b2b_revenue=b2b_revenue,
                               alerts=alerts,
                               feedbacks=feedbacks,          # Passed to frontend
                               call_requests=call_requests,  # Passed to frontend
                               pending_businesses=pending_businesses)
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
            delete_user_account(target_id)
            if data.get('alert_id'):
                db.reference(f"admin_alerts/{data.get('alert_id')}").delete()
            logger.info(f"GOD_MODE: User {target_id} banned.")
                
        elif action == 'approve_business':
            # Use East Africa Time for accurate 30-day windows
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
            
        # --- NEW ACTIONS FOR SUPPORT SYSTEM ---
        elif action == 'resolve_feedback':
            # We mapped the 'type' (suggestion or ticket) to the alert_id parameter in JS
            feedback_type = data.get('alert_id') 
            if feedback_type and target_id:
                db.reference(f'feedbacks/{feedback_type}/{target_id}').delete()
                
        elif action == 'resolve_call':
            if target_id:
                db.reference(f'call_requests/{target_id}').delete()
            
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Admin Action Error ({action}): {e}")
        return jsonify({'success': False, 'message': "Internal server error."}), 500

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

        # Print current time in EAT
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


import os
import logging
from datetime import datetime, timedelta
from flask import request, jsonify, session, flash, url_for

logger = logging.getLogger(__name__)

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
            # 2. Check if it's a mutual match
            target_swipe = db.reference(f'swipes/{target_user_id}/{current_user_id}').get()

            if target_swipe and target_swipe.get('action') == 'like':
                is_match = True
                match_id = "_".join(sorted([current_user_id, target_user_id]))
                
                # 3. Save Match Entry
                db.reference(f'matches/{match_id}').set({
                    'users': {current_user_id: True, target_user_id: True},
                    'matched_at': timestamp,
                    'last_message': 'You matched! Say hi.',
                    'last_message_time': timestamp
                })
                
                # 4. Prepare details for frontend popup
                target_profile = db.reference(f'profiles/{target_user_id}').get() or {}
                current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
                
                match_details = {
                    'name': target_profile.get('name', 'Your Match').split(' ')[0],
                    'img': target_profile.get('img', '/static/img/placeholder.png')
                }

                # 5. TRIGGER PUSH NOTIFICATION (Normal match buzz)
                current_name = current_profile.get('name', 'Someone').split(' ')[0]
                socketio.start_background_task(trigger_match_notification, target_user_id, current_name)

                # 6.  THE AI MAGIC: AI Wingman sends a tip to the current user
                socketio.start_background_task(ai_wingman_match_intro, current_user_id, target_profile)

        return jsonify({
            "status": "success",
            "match": is_match,
            "match_details": match_details
        })

    except Exception as e:
        logger.error(f"Swipe Error: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500
    
@app.route('/api/save-subscription', methods=['POST'])
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
def pay_student_fee():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    phone_number = request.json.get('phone_number')
    user_id = session.get('user_id')

    if not phone_number or not phone_number.startswith("254") or len(phone_number) != 12:
        return jsonify({'success': False, 'message': 'Phone format must be 2547XXXXXXXX'}), 400

    # Dynamically generate the callback URL for whichever environment you are currently running
    base_url = "https://www.findyourmatch.co.ke"
    callback_url = f"{base_url}/api/mpesa/student_callback"
    
    response = initiate_stk_push(phone_number, 20, user_id, callback_url)

    if 'error' in response:
        return jsonify({'success': False, 'message': 'Payment failed to initiate. Try again.'})

    if 'CheckoutRequestID' in response:
        checkout_id = response['CheckoutRequestID']
        # Temporarily link this specific transaction to this specific user
        db.reference(f'pending_payments/{checkout_id}').set(user_id)
        return jsonify({'success': True, 'message': 'Check your phone for the M-Pesa PIN prompt!'})
    
    return jsonify({'success': False, 'message': 'Payment failed to initiate.'})

@app.route('/api/mpesa/student_callback', methods=['POST'])
def mpesa_student_callback():
    data = request.json
    try:
        stk_callback = data['Body']['stkCallback']
        result_code = stk_callback['ResultCode']
        checkout_id = stk_callback['CheckoutRequestID']

        if result_code == 0:
            metadata = stk_callback['CallbackMetadata']['Item']
            mpesa_receipt = next((item['Value'] for item in metadata if item['Name'] == 'MpesaReceiptNumber'), None)
            
            # Lookup who initiated this exact transaction
            pending_ref = db.reference(f'pending_payments/{checkout_id}')
            user_id = pending_ref.get()

            if user_id:
                expiry_date = (datetime.now() + timedelta(days=30)).isoformat()
                db.reference(f'profiles/{user_id}').update({
                    'is_paid': True,
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': mpesa_receipt
                })
                # Clean up pending state
                pending_ref.delete()
                logger.info(f"✅ STUDENT ACTIVATED: {user_id} paid via {mpesa_receipt}")
            else:
                logger.warning(f"⚠️ Orphaned student payment received: {checkout_id}")
        else:
            fail_reason = stk_callback.get('ResultDesc', 'Unknown Error')
            logger.info(f"❌ STUDENT PAYMENT FAILED/CANCELLED: {fail_reason}")

    except Exception as e:
        logger.error(f"⚠️ Student Callback Error: {e}")

    # Always return 0 to Safaricom so they stop retrying the webhook
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

    if not receiver_id or not msg_text:
        return

    # 🚨 CRITICAL FIX FOR WHATSAPP SPEED 🚨
    data['sender'] = sender_id
    data['timestamp'] = datetime.now().isoformat()

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
                    'timestamp': datetime.now().isoformat()
                }, to=user_room)
            except Exception as e:
                logger.error(f"AI Worker Error: {e}")

        # Use SocketIO's safe background task instead of standard threading
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
                                'timestamp': datetime.now().isoformat()
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
    # ROUTE C: LIGHTNING FAST MESSAGE DELIVERY
    # ------------------------------------------
    
    # 1. SEND INSTANTLY (0ms delay for users)
    # Changed from request.sid to sender_id to support multi-device syncing
    emit('receive_message', data, to=sender_id) 
    emit('receive_message', data, to=receiver_id)

    # 2. SAVE IN BACKGROUND
    def background_save(s_id, r_id, text, m_type):
        try:
            save_chat_message(s_id, r_id, text, m_type)
        except Exception as e:
            logger.error(f"Failed to save chat message to DB: {e}")

    # Use SocketIO's safe background task manager
    socketio.start_background_task(background_save, sender_id, receiver_id, msg_text, msg_type)
    
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
    
    
if __name__ == '__main__':
    # Grab the port from Render's environment, default to 5000 for local testing
    port = int(os.environ.get('PORT', 5000))
    # You must listen on '0.0.0.0' for external traffic on a server!
    socketio.run(app, host='0.0.0.0', port=port, debug=False)