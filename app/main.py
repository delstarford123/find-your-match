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
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Define East Africa Time (UTC+3) for accurate Kenyan timestamps
EAT = timezone(timedelta(hours=3))

# Configure Central Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 2. LOCAL APP IMPORTS
# ==========================================
# 🔥 FIX: Added get_user_matches and create_date_booking!
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
        print(f"⚠️ User {target_user_id} has not enabled push notifications.")
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
        print(f"✅ Push notification instantly sent to {target_user_id}!")
    except WebPushException as ex:
        print(f"❌ Push failed: {repr(ex)}")
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
        # Ensure 'auth.login' matches your actual login blueprint/route name
        return redirect(url_for('auth.login')) 

    # 2. Fetch Fresh Data (The Source of Truth)
    # Always pull from the DB for the swipe deck so settings/images are never stale
    user_profile = db.reference(f'profiles/{user_id}').get() or {}

    # 3. Bundle Context for the Frontend
    current_user = {
        'id': user_id,
        # Split by space to get just their First Name for a friendlier UI
        'name': user_profile.get('name', session.get('user_name', 'Student')).split(' ')[0], 
        # Fallback to a placeholder if they haven't uploaded an image yet
        'img': user_profile.get('img') or url_for('static', filename='img/placeholder.png'),
        # Grab their latest filter preferences
        'settings': user_profile.get('settings', {}) 
    }

    return render_template(
        'swipe.html', 
        current_user=current_user
    ) 
@app.route('/dashboard')
@requires_subscription
def dashboard():
    # PROTECTED: Must be logged in AND paid
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
    my_matches = []
    
    if ai_mode:
        my_matches.append({
            'id': 'AI_COMPANION',
            'name': 'MMUST AI Companion 🤖',
            'bio': 'Your personal AI wingman and friend. Ready to chat!',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=MMUST&backgroundColor=ffccd5',
            'compatibility': 100
        })
    else:
        all_profiles = get_all_profiles()
        for p in all_profiles:
            if p['id'] != user_id and p.get('is_visible', True):
                my_matches.append({
                    'id': p['id'],
                    'name': p.get('name', 'Student').split(',')[0],
                    'bio': p.get('bio', 'MMUST Student'),
                    'img': p.get('img', 'https://via.placeholder.com/150'),
                    'compatibility': p.get('ai_score', 85)
                })

    return render_template('dashboard.html', current_user=session.get('user_name'), matches=my_matches)

@app.route('/matches')
@app.route('/matches/<partner_id>')
@requires_subscription
def matches(partner_id=None):
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    
    # Check if the user is in "Ghost Mode" (only talking to AI)
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
    my_matches = []
    
    if ai_mode:
        # If AI Mode is on, restrict the inbox to ONLY the AI Companion
        my_matches.append({
            'id': 'AI_COMPANION', 'name': 'AI Companion',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=MMUST&backgroundColor=ffccd5', 
            'is_perfect_match': True, 'is_online': True, 'is_mutual_match': True,
            'last_message': 'Ready to chat!', 'last_message_time': 'Just now'
        })
        partner_id = 'AI_COMPANION'
    else:
        # THE UPGRADE: Use the database helper to ONLY fetch mutual matches + AI Wingman
        my_matches = get_user_matches(user_id)
        
        # Sort the inbox so the most recently active chats float to the top
        my_matches.sort(key=lambda x: x.get('last_message_time', ''), reverse=True)
        
        # Auto-select the top chat if they just clicked "Messages" without a specific ID
        if not partner_id and my_matches:
            partner_id = my_matches[0]['id']

    # Find the data for the person currently being chatted with
    active_partner = next((m for m in my_matches if str(m['id']) == str(partner_id)), None)
    
    # Security Validation: Stop users from typing a random ID in the URL to spy on non-matches
    if partner_id and not active_partner and partner_id != 'AI_COMPANION':
        flash("You can only message students you have mutually matched with!", "warning")
        return redirect(url_for('matches'))

    # Load the chat history
    history = get_chat_history(user_id, partner_id) if active_partner else []
    
    return render_template('matches.html', 
                           current_user=session.get('user_name'), 
                           my_matches=my_matches, 
                           active_partner=active_partner, 
                           chat_history=history)
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

@app.route('/matchess')
@app.route('/matchess/<partner_ids>')
@requires_subscription
def matchess(partner_id=None):
    # PROTECTED: Must be logged in AND paid
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
    my_matches = []
    
    if ai_mode:
        # --- AI COMPANION MODE ---
        my_matches.append({
            'id': 'AI_COMPANION',
            'name': 'AI Companion',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=MMUST&backgroundColor=ffccd5', 
            'is_perfect_match': True,
            'is_online': True,
            'is_mutual_match': True, # AI is always a match
            'last_message': 'Ready to chat!',
            'last_message_time': 'Just now'
        })
        partner_id = 'AI_COMPANION'
    else:
        # --- HUMAN OPEN-DM MODE ---
        # 1. Fetch the mutual matches to see who gets the "MATCH" badge
        all_matches = db.reference('matches').get() or {}
        
        # Extract the partner IDs and chat metadata
        matched_data = {}
        for match_id, m_data in all_matches.items():
            if user_id in m_data.get('users', {}):
                # Find the ID of the *other* person in this match
                other_id = [uid for uid in m_data['users'].keys() if uid != user_id][0]
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
                
                # Check if this person is in the mutual match dictionary
                is_mutual = p_id in matched_data
                
                # Assign message text based on match status
                if is_mutual:
                    last_msg = matched_data[p_id]['last_message']
                    last_msg_time = matched_data[p_id]['last_message_time']
                else:
                    last_msg = 'Tap to start chatting'
                    last_msg_time = '' # Empty time pushes them down the list
                
                my_matches.append({
                    'id': p_id,
                    'name': p.get('name', 'Student').split(' ')[0], # First Name only
                    'img': p.get('img', '/static/img/placeholder.png'),
                    'is_perfect_match': p.get('ai_score', 0) > 80,
                    'is_online': p.get('is_online', False),
                    'is_mutual_match': is_mutual, # 🔥 THIS POWERS THE HTML GLOW EFFECT
                    'last_message': last_msg,
                    'last_message_time': last_msg_time
                })
        
        # 4. Sort the inbox: Mutual Matches with recent chats float to the top
        # We sort by is_mutual_match (True first), then by time
        my_matches.sort(
            key=lambda x: (x['is_mutual_match'], x.get('last_message_time', '')), 
            reverse=True
        )

        # 5. Auto-select the top chat if no specific partner_id is in the URL
        if not partner_id and my_matches:
            partner_id = my_matches[0]['id']

    # Find the data for the person currently being chatted with
    active_partner = next((m for m in my_matches if str(m['id']) == str(partner_id)), None)
    
    # Validation: Ensure the user isn't typing a fake ID in the URL
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
        flash("Profile not found.", "error")
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        new_bio = request.form.get('bio')
        new_age = request.form.get('age')
        new_religion = request.form.get('religion')

        try:
            user_ref.update({
                'bio': new_bio if new_bio else user_data.get('bio'),
                'age': int(new_age) if new_age else user_data.get('age'),
                'religion': new_religion if new_religion else user_data.get('religion')
            })
            
            if new_religion:
                session['user_religion'] = new_religion

            days = request.form.getlist('day_of_week[]')
            starts = request.form.getlist('start_time[]')
            ends = request.form.getlist('end_time[]')
            
            for i in range(len(days)):
                if days[i] and starts[i] and ends[i]:
                    save_schedule(user_id, days[i], starts[i], ends[i])
            
            flash("Profile and Free Time Schedule updated successfully!", "success")
            return redirect(url_for('profile'))
            
        except Exception as e:
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
        gender_pref = request.form.get('gender_pref')
        major_filter = request.form.get('major_filter')
        strict_mode = request.form.get('strict_mode') == 'on'
        ai_mode = request.form.get('ai_mode') == 'on'

        try:
            # Save settings to the 'settings' sub-node
            user_ref.child('settings').update({
                'looking_for': gender_pref,
                'major_filter': major_filter,
                'strict_schedule': strict_mode,
                'ai_companion_mode': ai_mode
            })
            
            # Update main profile visibility
            user_ref.update({
                'is_visible': not ai_mode 
            })
            
            flash("Discovery settings updated successfully!", "success")
        except Exception as e:
            flash("Error saving settings to cloud.", "error")

        return redirect(url_for('settings'))

    # === GET REQUEST LOGIC (THE FIX) ===
    # 1. Fetch the user's data from Firebase
    user_profile = user_ref.get() or {}
    user_settings = user_profile.get('settings', {})

    # 2. Map the Firebase keys to the variable names the HTML template expects
    template_user_data = {
        'gender_pref': user_settings.get('looking_for', 'Everyone'),
        'major_filter': user_settings.get('major_filter', 'All'),
        'strict_mode': user_settings.get('strict_schedule', False),
        'ai_mode': user_settings.get('ai_companion_mode', False)
    }

    # 3. Pass the mapped data to the template
    return render_template(
        'settings.html', 
        current_user=session.get('user_name'),
        user=template_user_data
    )
# ==========================================
# B2B PAGES (MERCHANTS)
# ==========================================
@app.route('/business/dashboard')
def business_dashboard():
    if session.get('account_type') != 'business':
        flash("Access Denied. This portal is for registered businesses only.", "error")
        return redirect(url_for('home'))

    restaurant_id = session.get('business_id')
    restaurant = get_restaurant(restaurant_id) or {}
    
    # === THE FIX: Add default empty values for new restaurants ===
    if 'hourly_stats' not in restaurant:
        restaurant['hourly_stats'] = {}
    if 'qr_scans' not in restaurant:
        restaurant['qr_scans'] = 0
    # =============================================================

    bookings = get_restaurant_bookings(restaurant_id)
    
    pending_count = sum(1 for b in bookings if b.get('status') == 'Pending')
    approved_count = sum(1 for b in bookings if b.get('status') == 'Approved')
    
    for b in bookings:
        b['user_a_name'] = "Student 1" 
        b['user_b_name'] = "Student 2"

    return render_template('business_dashboard.html', 
                           restaurant=restaurant, 
                           bookings=bookings,
                           pending_count=pending_count,
                           approved_count=approved_count)
    
@app.route('/business/booking/<booking_id>/<action>', methods=['POST'])
def manage_booking(booking_id, action):
    if session.get('account_type') != 'business':
        return redirect(url_for('home'))
        
    status = 'Approved' if action == 'approve' else 'Declined'
    update_booking_status(booking_id, status)
    flash(f"Reservation successfully {status.lower()}!", "success")
    return redirect(url_for('business_dashboard'))

@app.route('/business/qr')
def merchant_qr():
    if session.get('account_type') != 'business':
        return redirect(url_for('home'))

    restaurant_id = session.get('business_id')
    restaurant_name = session.get('business_name')

    base_url = request.url_root.rstrip('/')
    verify_url = f"{base_url}/verify_customer/{restaurant_id}"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(verify_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#800000", back_color="white")
    
    buf = io.BytesIO()
    img.save(buf)
    image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return render_template('merchant_qr.html', 
                           qr_code=image_base64, 
                           restaurant_name=restaurant_name)

@app.route('/verify_customer/<restaurant_id>')
def verify_customer(restaurant_id):
    if 'user_id' not in session:
        flash("Please log in to verify your student discount.", "warning")
        return redirect(url_for('auth.login'))

    user_id = session.get('user_id')
    
    try:
        user_data = db.reference(f'profiles/{user_id}').get()
        restaurant = db.reference(f'restaurants/{restaurant_id}').get()
    except Exception as e:
        print(f"Firebase Fetch Error: {e}")
        flash("Database connection error. Please try again.", "error")
        return redirect(url_for('dashboard'))

    if not restaurant:
        flash("Invalid QR Code. This venue is not part of our network.", "error")
        return redirect(url_for('dashboard'))

    if not user_data or not user_data.get('is_paid'):
        status = "REJECTED"
        message = "No active subscription found. Pay 20 KSH to unlock discounts."
        color = "#ef4444"
    else:
        status = "VERIFIED"
        perk = restaurant.get('conditions', 'Standard Student Discount')
        message = f"Valid Student Subscriber! Apply the '{perk}' discount."
        color = "#10b981"
        
        try:
            qr_ref = db.reference(f'restaurants/{restaurant_id}/qr_scans')
            current_scans = qr_ref.get() or 0
            qr_ref.set(current_scans + 1)

            current_hour = datetime.now().hour
            hour_ref = db.reference(f'restaurants/{restaurant_id}/hourly_stats/{current_hour}')
            current_hour_count = hour_ref.get() or 0
            hour_ref.set(current_hour_count + 1)

            alert_ref = db.reference(f'merchant_alerts/{restaurant_id}')
            alert_ref.set({
                'student_name': user_data.get('name'),
                'reg_number': user_data.get('reg_number'),
                'timestamp': datetime.now().isoformat(),
                'status': 'new'
            })
            
        except Exception as e:
            print(f"Error updating merchant analytics: {e}")

    return render_template('verification_result.html', 
                           status=status, 
                           message=message, 
                           color=color,
                           restaurant_name=restaurant.get('business_name'))
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
        # FIXED: Pointing to super_admin.html
        return render_template('super_admin.html', logged_in=False)

    try:
        # Fetch Data
        all_profiles = db.reference('profiles').get() or {}
        all_restaurants = db.reference('restaurants').get() or {}
        alerts_dict = db.reference('admin_alerts').get() or {}
        
        # Calculate Revenue
        student_revenue = sum(20 for p in all_profiles.values() if p.get('is_paid'))
        b2b_revenue = sum(2000 for r in all_restaurants.values() if r.get('subscription_active'))
        total_revenue = student_revenue + b2b_revenue

        # Format and Sort Alerts (Newest First)
        alerts = [{'alert_id': k, **v} for k, v in alerts_dict.items()]
        alerts.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

        # Filter Pending Businesses
        pending_businesses = [
            {'id': k, **v} for k, v in all_restaurants.items() 
            if not v.get('subscription_active')
        ]

        # FIXED: Pointing to super_admin.html
        return render_template('super_admin.html', 
                               logged_in=True,
                               total_revenue=total_revenue,
                               student_revenue=student_revenue,
                               b2b_revenue=b2b_revenue,
                               alerts=alerts,
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
        
        paid_students = [p for p in profiles.values() if p.get('is_paid')]
        student_revenue = len(paid_students) * 20
        
        active_merchants = [r for r in restaurants.values() if r.get('subscription_active')]
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
    base_url = os.getenv("BASE_URL", request.host_url.rstrip('/'))
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
    if session.get('account_type') != 'business':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    phone_number = data.get('phone_number')
    restaurant_id = session.get('business_id')

    if not phone_number or not phone_number.startswith("254") or len(phone_number) != 12:
        return jsonify({'error': 'Format must be 2547XXXXXXXX'}), 400

    base_url = os.getenv("BASE_URL", request.host_url.rstrip('/'))
    callback_url = f"{base_url}/api/mpesa/b2b_callback"
    
    response = initiate_stk_push(phone_number, 2000, restaurant_id, callback_url)

    if 'error' in response:
        return jsonify({'success': False, 'message': 'Payment initiation failed. Try again.'})
    
    if 'CheckoutRequestID' in response:
        checkout_id = response['CheckoutRequestID']
        # Securely link the transaction to the merchant
        db.reference(f'pending_b2b_payments/{checkout_id}').set(restaurant_id)
        return jsonify({'success': True, 'message': 'STK Push sent! Enter your M-Pesa PIN.'})

    return jsonify({'success': False, 'message': 'Payment failed.'})


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
            
            # 1. Save to Financial Ledger
            db.reference('ledger').push({
                'type': 'B2B',
                'amount': amount,
                'receipt': receipt,
                'phone': phone,
                'timestamp': datetime.now().isoformat(),
                'status': 'Completed'
            })
            logger.info(f"💰 M-Pesa B2B Payment Received: {amount} KSH (Receipt: {receipt})")

            # 2. ACTIVATE THE MERCHANT
            pending_ref = db.reference(f'pending_b2b_payments/{checkout_id}')
            restaurant_id = pending_ref.get()

            if restaurant_id:
                expiry_date = (datetime.now() + timedelta(days=30)).isoformat()
                db.reference(f'restaurants/{restaurant_id}').update({
                    'subscription_active': True,
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': receipt
                })
                pending_ref.delete()
                logger.info(f"✅ MERCHANT ACTIVATED: ID {restaurant_id}")
            else:
                logger.warning(f"⚠️ Payment received, but could not find matching merchant for checkout: {checkout_id}")

        else:
            fail_reason = stk_callback.get('ResultDesc', 'Unknown Error')
            logger.info(f"❌ M-Pesa B2B Payment Failed: {fail_reason}")

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
@login_required
def discover_venues():
    user_id = session.get('user_id')
    
    # 1. Fetch only ACTIVE (paying) restaurants
    venues = get_all_restaurants(active_only=True)
    
    # 2. Fetch the user's active matches for the dropdown
    my_matches = get_user_matches(user_id) 
    
    return render_template('bookings.html', venues=venues, matches=my_matches)

@app.route('/api/propose_date', methods=['POST'])
@login_required
def propose_date():
    """Handles the booking request and sends a real-time invite in the chat."""
    data = request.json
    sender_id = session.get('user_id')
    
    venue_id = data.get('venue_id')
    venue_name = data.get('venue_name')
    partner_id = data.get('partner_id')
    date_day = data.get('day')
    date_time = data.get('time')
    
    if not all([venue_id, partner_id, date_day, date_time]):
        return jsonify({'success': False, 'message': 'Missing details.'}), 400
        
    try:
        # 1. Create the pending booking for the merchant
        create_date_booking(venue_id, sender_id, partner_id, date_day, date_time)
        
        # 2. Increment venue profile views
        increment_restaurant_view(venue_id)
        
        # 3. Format & Save the chat message
        invite_msg = (
            f"💌 **DATE INVITATION** 💌\n\n"
            f"I'd love to take you to **{venue_name}**!\n"
            f"📅 **When:** {date_day} at {date_time}\n"
            f"Let me know if you're down!"
        )
        save_chat_message(sender_id, partner_id, invite_msg, msg_type='date_invite')
        
        # 4. REAL-TIME SYNC: Push the message instantly to the partner's screen
        socket_payload = {
            'sender': sender_id,
            'receiver_id': partner_id,
            'type': 'date_invite',
            'text': invite_msg,
            'timestamp': datetime.now(EAT).isoformat(),
            'temp_id': f"invite_{int(datetime.now().timestamp())}"
        }
        
        try:
            socketio.emit('receive_message', socket_payload, to=partner_id)
        except Exception as sock_err:
            logger.warning(f"Socket emit failed (partner might be offline): {sock_err}")

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
    user_id = session.get('user_id')
    user_profile = db.reference(f'profiles/{user_id}').get() or {}
    my_matches = get_user_matches(user_id) 
    
    return render_template('wingman.html', user=user_profile, matches=my_matches)

@app.route('/api/wingman_action', methods=['POST'])
@login_required
def api_wingman_action():
    """Handles requests for Profile Roasts and Icebreakers."""
    data = request.json
    action = data.get('action')
    user_id = session.get('user_id')
    
    try:
        if action == 'roast_profile':
            user_profile = db.reference(f'profiles/{user_id}').get() or {}
            bio = user_profile.get('bio', 'No bio provided.')
            major = user_profile.get('major', 'Unknown major.')
            
            prompt = (
                f"Act as a brutally honest, funny, but ultimately helpful college dating coach. "
                f"My major is {major} and my dating app bio is: '{bio}'. "
                f"Give me a funny 'roast' of this bio, and then provide 3 actionable tips "
                f"or rewrite suggestions to make it more attractive to college students."
            )
            
            ai_response = get_ai_companion_response(prompt, user_gender=user_profile.get('gender', 'unknown'))
            return jsonify({'success': True, 'response': ai_response})
            
        elif action == 'generate_icebreaker':
            partner_id = data.get('partner_id')
            if not partner_id:
                return jsonify({'success': False, 'message': 'Select a match first!'}), 400
                
            partner_profile = db.reference(f'profiles/{partner_id}').get() or {}
            partner_bio = partner_profile.get('bio', 'They have no bio... time to get creative.')
            partner_name = partner_profile.get('name', 'your match').split(',')[0]
            
            prompt = (
                f"Act as my ultimate wingman. I just matched with someone named {partner_name}. "
                f"Their bio says: '{partner_bio}'. "
                f"Generate 3 highly customized, funny, and engaging icebreakers I can send them right now. "
                f"Don't be creepy. Keep it fun and college-appropriate."
            )
            
            ai_response = get_ai_companion_response(prompt, user_gender='unknown')
            return jsonify({'success': True, 'response': ai_response})
            
        else:
            return jsonify({'success': False, 'message': 'Invalid action.'}), 400

    except Exception as e:
        logger.error(f"Wingman API Error: {e}")
        return jsonify({'success': False, 'message': 'The Wingman is currently busy. Try again later!'}), 500  
         
if __name__ == '__main__':
    # Grab the port from Render's environment, default to 5000 for local testing
    port = int(os.environ.get('PORT', 5000))
    # You must listen on '0.0.0.0' for external traffic on a server!
    socketio.run(app, host='0.0.0.0', port=port, debug=False)