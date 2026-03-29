import os
import sys
import time
import random
import io
import base64
import qrcode
import json
import threading
from datetime import datetime, timedelta
from dotenv import load_dotenv

from flask import Flask, render_template, session, redirect, url_for, flash, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
from pywebpush import webpush, WebPushException

# 1. Path Setup & Environment
load_dotenv()
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 2. Local App Imports
from app.database import (
    db, get_all_profiles, save_schedule, update_user_bio, 
    save_chat_message, get_chat_history, save_swipe, save_date_feedback,
    get_restaurant, get_restaurant_bookings, update_booking_status, terminate_connection,
    get_all_restaurants, delete_user_account, increment_restaurant_view
)
from app.services.recommendation_engine import generate_ranked_deck
from app.services.moderation import contains_phone_number, analyze_safety
from app.payments import initiate_stk_push

# ==========================================
# AI INTEGRATION: LOAD THE FINE-TUNED BRAIN
# ==========================================
try:
    from loveai.src.predict import generate_response, load_model
    print("🚀 Initializing Local AI Brain (TinyLlama + MMUST LoRA)...")
    load_model() 
except Exception as e:
    print(f"⚠️ AI Model failed to load. Error: {e}")
    generate_response = None # Fallback


# 3. Initialize App & WebSockets
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "delstarford_works_secret_2026")

# VAPID Keys for Push Notifications
app.config['VAPID_PRIVATE_KEY'] = "private_key.pem" 
app.config['VAPID_CLAIMS'] = {"sub": "mailto:delstarfordisaiah@gmail.com"}

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 4. Register Blueprints
from app.routes.auth import auth_bp
app.register_blueprint(auth_bp)


# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_ai_companion_response(user_text):
    """Connects the Flask app to your local LoRA fine-tuned model."""
    if generate_response is None:
        return "My AI brain is currently resting. Please check the server logs!"

    try:
        reply = generate_response(user_text)
        if not reply or len(reply.strip()) == 0:
            return "I'm thinking about that... what else is on your mind?"
        return reply
    except Exception as e:
        print(f"⚠️ AI Generation Error: {e}")
        return "I'm having a bit of a 'comrade' moment (my brain is lagging). Can you say that again?"

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
# CORE B2C PAGES (STUDENTS)
# ==========================================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/safety')
def safety():
    return render_template('safety.html', current_user=session.get('user_name'))

@app.route('/privacy')
def privacy():
    return render_template('privacy.html', current_user=session.get('user_name'))

@app.route('/terms')
def terms():
    return render_template('terms.html', current_user=session.get('user_name'))

@app.route('/venues')
def venues():
    active_venues = get_all_restaurants(active_only=True)
    return render_template('venues.html', current_user=session.get('user_name'), venues=active_venues)

@app.route('/swipe')
def swipe():
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))
        
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get()
    
    if not user_data or not user_data.get('is_paid', False):
        flash("Subscription Required: Please pay 20 KSH to access the Swipe Deck.", "warning")
        return render_template('paywall.html') 
        
    return render_template('swipe.html', current_user=session.get('user_name'))

@app.route('/dashboard')
def dashboard():
    if 'user_email' not in session:
        flash("Please log in to view your dashboard.", "error")
        return redirect(url_for('auth.login'))

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
def matches(partner_id=None):
    if 'user_email' not in session:
        return redirect(url_for('auth.signup'))
    
    user_id = session.get('user_id')
    user_data = db.reference(f'profiles/{user_id}').get() or {}
    ai_mode = user_data.get('settings', {}).get('ai_companion_mode') == True
    
    my_matches = []
    
    if ai_mode:
        my_matches.append({
            'id': 'AI_COMPANION',
            'name': 'AI Companion',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=MMUST&backgroundColor=ffccd5', 
            'is_perfect_match': True,
            'is_online': True
        })
        partner_id = 'AI_COMPANION'
    else:
        all_profiles = get_all_profiles()
        for p in all_profiles:
            if p['id'] != user_id and p.get('is_visible', True): 
                my_matches.append({
                    'id': p['id'],
                    'name': p.get('name', 'Student').split(',')[0],
                    'img': p.get('img', 'https://via.placeholder.com/150'),
                    'is_perfect_match': p.get('ai_score', 0) > 80,
                    'is_online': True 
                })

        if not partner_id and my_matches:
            partner_id = my_matches[0]['id']

    active_partner = next((m for m in my_matches if str(m['id']) == str(partner_id)), None)
    history = get_chat_history(user_id, partner_id) if partner_id else []
    
    return render_template('matches.html', 
                           current_user=session.get('user_name'),
                           my_matches=my_matches,
                           active_partner=active_partner,
                           chat_history=history)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_email' not in session:
        flash("Please log in to view your profile.", "error")
        return redirect(url_for('auth.login'))

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
def view_student(target_id):
    if 'user_email' not in session:
        return redirect(url_for('auth.login'))

    all_profiles = get_all_profiles()
    student_profile = next((p for p in all_profiles if p['id'] == target_id), None)
    
    if not student_profile:
        flash("Oops! We couldn't find that student's profile.", "error")
        return redirect(url_for('dashboard'))
        
    return render_template('view_profile.html', student=student_profile)

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user_email' not in session:
        flash("Please log in to change your settings.", "error")
        return redirect(url_for('auth.login'))
    
    user_id = session.get('user_id')

    if request.method == 'POST':
        gender_pref = request.form.get('gender_pref')
        major_filter = request.form.get('major_filter')
        strict_mode = request.form.get('strict_mode') == 'on'
        ai_mode = request.form.get('ai_mode') == 'on'

        try:
            ref = db.reference(f'profiles/{user_id}/settings')
            ref.update({
                'looking_for': gender_pref,
                'major_filter': major_filter,
                'strict_schedule': strict_mode,
                'ai_companion_mode': ai_mode
            })
            
            db.reference(f'profiles/{user_id}').update({
                'is_visible': not ai_mode 
            })
            
            flash("Discovery settings updated successfully!", "success")
        except Exception as e:
            flash("Error saving settings to cloud.", "error")

        return redirect(url_for('settings'))

    return render_template('settings.html', current_user=session.get('user_name'))

# ==========================================
# B2B PAGES (MERCHANTS)
# ==========================================

@app.route('/business/dashboard')
def business_dashboard():
    if session.get('account_type') != 'business':
        flash("Access Denied. This portal is for registered businesses only.", "error")
        return redirect(url_for('home'))

    restaurant_id = session.get('business_id')
    restaurant = get_restaurant(restaurant_id)
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

# ==========================================
# GOD MODE: SUPER ADMIN DASHBOARD
# ==========================================

@app.route('/admin/super', methods=['GET', 'POST'])
def super_admin():
    ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASS", "delstarford2026")
    
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['is_super_admin'] = True
            flash("Welcome to God Mode, Creator.", "success")
        else:
            flash("Access Denied. Incorrect Password.", "error")
        return redirect(url_for('super_admin'))
        
    if not session.get('is_super_admin'):
        return render_template('super_admin.html', logged_in=False)

    all_profiles = db.reference('profiles').get() or {}
    all_restaurants = db.reference('restaurants').get() or {}
    
    student_revenue = sum(20 for p in all_profiles.values() if p.get('is_paid'))
    b2b_revenue = sum(2000 for r in all_restaurants.values() if r.get('subscription_active'))
    total_revenue = student_revenue + b2b_revenue

    alerts_dict = db.reference('admin_alerts').get() or {}
    alerts = [{'alert_id': k, **v} for k, v in alerts_dict.items()]

    pending_businesses = [{'id': k, **v} for k, v in all_restaurants.items() if not v.get('subscription_active')]

    return render_template('super_admin.html', 
                           logged_in=True,
                           total_revenue=total_revenue,
                           student_revenue=student_revenue,
                           b2b_revenue=b2b_revenue,
                           alerts=alerts,
                           pending_businesses=pending_businesses)

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
                
        elif action == 'approve_business':
            expiry = (datetime.now() + timedelta(days=30)).isoformat()
            db.reference(f'restaurants/{target_id}').update({
                'subscription_active': True,
                'subscription_expiry': expiry
            })
            
        elif action == 'dismiss_alert':
            db.reference(f'admin_alerts/{target_id}').delete()
            
        return jsonify({'success': True})
    except Exception as e:
        print(f"Admin Action Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/admin/ledger')
def admin_ledger():
    if not session.get('is_super_admin'):
        return redirect(url_for('home'))

    profiles = db.reference('profiles').get() or {}
    restaurants = db.reference('restaurants').get() or {}
    
    paid_students = [p for p in profiles.values() if p.get('is_paid')]
    student_revenue = len(paid_students) * 20
    
    active_merchants = [r for r in restaurants.values() if r.get('subscription_active')]
    merchant_revenue = len(active_merchants) * 2000
    
    total_revenue = student_revenue + merchant_revenue

    return render_template('admin_ledger.html', 
                           student_count=len(paid_students),
                           student_rev=student_revenue,
                           merchant_count=len(active_merchants),
                           merchant_rev=merchant_revenue,
                           total_rev=total_revenue,
                           last_updated=datetime.now().strftime("%Y-%m-%d %H:%M"))

# ==========================================
# API ENDPOINTS (SWIPE, PAYMENTS, NOTIFICATIONS)
# ==========================================

@app.route('/api/profiles')
def get_profiles():
    user_id = request.args.get('user_id')
    ranked_deck = generate_ranked_deck(user_id)
    return jsonify(ranked_deck)

@app.route('/api/swipe', methods=['POST'])
def record_swipe():
    if 'user_id' not in session:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    data = request.json
    current_user_id = session.get('user_id')
    target_user_id = data.get('target_id')
    action = data.get('action') 
    timestamp = datetime.now().isoformat()

    if not target_user_id or not action:
        return jsonify({"status": "error", "message": "Missing swipe data"}), 400

    try:
        db.reference(f'swipes/{current_user_id}/{target_user_id}').set({
            'action': action,
            'timestamp': timestamp
        })
    except Exception as e:
        print(f"Database Error saving swipe: {e}")
        return jsonify({"status": "error", "message": "Database failed"}), 500

    is_match = False
    match_details = {}

    if action == 'like':
        target_swipe = db.reference(f'swipes/{target_user_id}/{current_user_id}').get()

        if target_swipe and target_swipe.get('action') == 'like':
            is_match = True
            match_id = "_".join(sorted([current_user_id, target_user_id]))
            
            db.reference(f'matches/{match_id}').set({
                'users': {current_user_id: True, target_user_id: True},
                'matched_at': timestamp,
                'last_message': 'You matched! Say hi.',
                'last_message_time': timestamp
            })

            current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
            target_profile = db.reference(f'profiles/{target_user_id}').get() or {}

            current_name = current_profile.get('name', 'Someone').split(' ')[0]
            target_name = target_profile.get('name', 'Your Match').split(' ')[0]
            
            match_details = {
                'name': target_name,
                'img': target_profile.get('img', '/static/img/placeholder.png')
            }

            try:
                trigger_match_notification(target_user_id, current_name)
            except Exception as e:
                print(f"Failed to send push notification: {e}")

    return jsonify({
        "status": "success",
        "match": is_match,
        "match_details": match_details
    })

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
        print(f"Error saving subscription: {e}")
        return jsonify({"status": "error", "message": "Database error"}), 500

@app.route('/api/end_date', methods=['POST'])
def end_date():
    if 'user_id' not in session: return jsonify({'error': 'Unauthorized'}), 403
    user_id = session.get('user_id')
    partner_id = request.json.get('partner_id')
    
    if terminate_connection(user_id, partner_id):
        flash("Date terminated. All data and chats have been securely deleted.", "success")
        return jsonify({'success': True})
    return jsonify({'success': False}), 500

@app.route('/api/pay_student_fee', methods=['POST'])
def pay_student_fee():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 403

    phone_number = request.json.get('phone_number')
    user_id = session.get('user_id')

    if not phone_number or not phone_number.startswith("254") or len(phone_number) != 12:
        return jsonify({'success': False, 'message': 'Phone format must be 2547XXXXXXXX'}), 400

    callback_url = "https://YOUR_DOMAIN.com/api/mpesa/student_callback"
    response = initiate_stk_push(phone_number, 20, user_id, callback_url)

    if 'error' in response:
        return jsonify({'success': False, 'message': 'Payment failed to initiate. Try again.'})

    if 'CheckoutRequestID' in response:
        checkout_id = response['CheckoutRequestID']
        db.reference(f'pending_payments/{checkout_id}').set(user_id)
        return jsonify({'success': True, 'message': 'Check your phone for the M-Pesa PIN prompt!'})
    
    return jsonify({'success': False, 'message': 'Payment failed to initiate.'})

@app.route('/api/mpesa/student_callback', methods=['POST'])
def mpesa_student_callback():
    callback_data = request.json
    try:
        stk_callback = callback_data['Body']['stkCallback']
        result_code = stk_callback['ResultCode']
        checkout_id = stk_callback['CheckoutRequestID']

        if result_code == 0:
            metadata = stk_callback['CallbackMetadata']['Item']
            mpesa_receipt = next((item['Value'] for item in metadata if item['Name'] == 'MpesaReceiptNumber'), None)
            
            pending_ref = db.reference(f'pending_payments/{checkout_id}')
            user_id = pending_ref.get()

            if user_id:
                expiry_date = (datetime.now() + timedelta(days=30)).isoformat()
                db.reference(f'profiles/{user_id}').update({
                    'is_paid': True,
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': mpesa_receipt
                })
                pending_ref.delete()
                print(f"✅ STUDENT ACTIVATED: {user_id} paid via {mpesa_receipt}")
        else:
            print(f"❌ STUDENT PAYMENT FAILED: Code {result_code}")

    except Exception as e:
        print(f"⚠️ Callback Error: {e}")

    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})

@app.route('/api/pay_subscription', methods=['POST'])
def pay_subscription():
    if session.get('account_type') != 'business':
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json
    phone_number = data.get('phone_number')
    restaurant_id = session.get('business_id')

    if not phone_number or not phone_number.startswith("254") or len(phone_number) != 12:
        return jsonify({'error': 'Format must be 2547XXXXXXXX'}), 400

    callback_url = "https://YOUR_DOMAIN.com/api/mpesa/callback"
    response = initiate_stk_push(phone_number, 2000, restaurant_id, callback_url)

    if 'error' in response:
        return jsonify({'success': False, 'message': 'Payment initiation failed. Try again.'})
    
    return jsonify({'success': True, 'message': 'STK Push sent! Enter your M-Pesa PIN.'})

@app.route('/api/mpesa/callback', methods=['POST'])
def mpesa_callback():
    callback_data = request.json
    try:
        result_code = callback_data['Body']['stkCallback']['ResultCode']
        if result_code == 0:
            restaurant_id = "FETCHED_RESTAURANT_ID" # You'll need to fetch this from a pending_payments table similar to students
            ref = db.reference(f'restaurants/{restaurant_id}')
            ref.update({
                'subscription_active': True,
                'subscription_expiry': (datetime.now() + timedelta(days=30)).isoformat()
            })
            print(f"💰 SUCCESS: Subscription activated for {restaurant_id}")
    except Exception as e:
        print(f"❌ Webhook parsing error: {e}")
    return jsonify({"ResultCode": 0, "ResultDesc": "Accepted"})


# ==========================================
# WEBSOCKETS (CHAT, AI COMPANION & SAFETY)
# ==========================================

@socketio.on('typing')
def handle_typing(data):
    emit('user_typing', data, broadcast=True, include_self=False)

@socketio.on('send_message')
def handle_message(data):
    sender_id = session.get('user_id')
    receiver_id = data.get('receiver_id')
    msg_text = data.get('text')
    msg_type = data.get('type', 'text')

    if receiver_id == 'AI_COMPANION':
        emit('receive_message', data, to=request.sid)
        emit('user_typing', {'sender': 'AI_COMPANION', 'is_typing': True}, to=request.sid)
        
        def ai_worker(query, sid):
            ai_reply = get_ai_companion_response(query)
            socketio.emit('user_typing', {'sender': 'AI_COMPANION', 'is_typing': False}, to=sid)
            socketio.emit('receive_message', {
                'sender': 'AI_COMPANION',
                'type': 'text',
                'text': ai_reply
            }, to=sid)

        threading.Thread(target=ai_worker, args=(msg_text, request.sid)).start()
        return

    if msg_type == 'text':
        safety_check = analyze_safety(msg_text)
        if not safety_check['is_safe']:
            if safety_check['flag'] in ['self_harm', 'violence']:
                db.reference('admin_alerts').push({
                    'sender': sender_id,
                    'receiver': receiver_id,
                    'message': msg_text,
                    'flag': safety_check['flag'],
                    'timestamp': datetime.now().isoformat()
                })
            warning_msg = {'sender': 'SYSTEM_AI', 'type': 'text', 'text': safety_check['system_reply']}
            emit('receive_message', warning_msg, to=request.sid) 
            return

        if contains_phone_number(msg_text):
            warning_msg = {
                'sender': 'SYSTEM_AI',
                'type': 'text',
                'text': "SYSTEM ALERT: Sharing phone numbers is restricted for your safety."
            }
            emit('receive_message', warning_msg, to=request.sid) 
            return

    save_chat_message(sender_id, receiver_id, msg_text, msg_type)
    emit('receive_message', data, broadcast=True)


if __name__ == '__main__':
    socketio.run(app, debug=True, use_reloader=False)