import os
import logging
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db, storage

# ==========================================
# 1. CONFIGURATION & INITIALIZATION
# ==========================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# East Africa Time (UTC+3) for accurate Kenyan timestamps
EAT = timezone(timedelta(hours=3))

CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../firebase_key.json'))
DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")

def initialize_firebase():
    """Initializes the Firebase Admin SDK safely (Singleton pattern)."""
    if not firebase_admin._apps:
        try:
            import json
            cred_json = os.getenv("FIREBASE_CREDENTIALS")
            if cred_json:
                # Load from environment variable (Vercel)
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
            elif os.path.exists(CREDENTIALS_PATH):
                # Load from local file
                cred = credentials.Certificate(CREDENTIALS_PATH)
            else:
                logger.error(f"Missing Firebase credentials. Neither FIREBASE_CREDENTIALS env var nor {CREDENTIALS_PATH} found.")
                return
                
            firebase_admin.initialize_app(cred, {
                'databaseURL': DATABASE_URL,
                'storageBucket': os.getenv("FIREBASE_STORAGE_BUCKET", "mmust-dating-site.firebasestorage.app")
            })
            logger.info("🔥 Firebase Realtime Database connected successfully!")
        except Exception as e:
            logger.error(f"❌ Firebase Connection Error: {e}")

# Run initialization immediately upon import
initialize_firebase()


# ==========================================
# DATABASE HELPER FUNCTIONS (STUDENT USERS)
# ==========================================

_profiles_cache = None
_profiles_cache_expiry = None

def get_all_profiles() -> list:
    """Fetches all students from the 'profiles' node with a 15-second cache buffer for speed."""
    global _profiles_cache, _profiles_cache_expiry
    try:
        now = datetime.now()
        if _profiles_cache is not None and _profiles_cache_expiry is not None and now < _profiles_cache_expiry:
            return _profiles_cache

        users_dict = db.reference('profiles').get()
        if not users_dict:
            return []
        
        profiles = [{**data, 'id': uid} for uid, data in users_dict.items() if data]
        _profiles_cache = profiles
        _profiles_cache_expiry = now + timedelta(seconds=15)
        return profiles
    except Exception as e:
        logger.error(f"Error fetching profiles: {e}")
        if _profiles_cache is not None:
            return _profiles_cache
        return []

def clear_profiles_cache():
    """Manually invalidates the memory cache to force a fresh database read."""
    global _profiles_cache, _profiles_cache_expiry
    _profiles_cache = None
    _profiles_cache_expiry = None

def save_swipe(user_id: str, target_id: str, action: str, timestamp: str) -> str:
    """Pushes a new swipe record and returns its generated ID."""
    try:
        clear_profiles_cache()
        new_ref = db.reference('swipes').push({
            'user_id': user_id,
            'target_id': target_id,
            'action': action,
            'timestamp': timestamp
        })
        return new_ref.key
    except Exception as e:
        logger.error(f"Error saving swipe: {e}")
        return ""

def get_all_swipes() -> list:
    """Fetches all swipes for the ML Collaborative Filtering model."""
    try:
        swipes_dict = db.reference('swipes').get()
        return list(swipes_dict.values()) if swipes_dict else []
    except Exception as e:
        logger.error(f"Error fetching swipes: {e}")
        return []

def save_schedule(user_id: str, day_of_week: str, start_time: str, end_time: str) -> bool:
    """Pushes a free-time block to the user's schedule."""
    try:
        db.reference('schedules').push({
            'user_id': user_id,
            'day_of_week': day_of_week,
            'start_time': start_time,
            'end_time': end_time
        })
        return True
    except Exception as e:
        logger.error(f"Error saving schedule: {e}")
        return False

def get_all_schedules() -> list:
    """Fetches all schedules for the AI Matcher algorithm."""
    try:
        schedules_dict = db.reference('schedules').get()
        return list(schedules_dict.values()) if schedules_dict else []
    except Exception as e:
        logger.error(f"Error fetching schedules: {e}")
        return []

def save_date_feedback(user_id: str, target_id: str, did_meet: bool, vibe_rating: str) -> bool:
    """Saves post-date feedback for the 'Holy Grail' ML reinforcement loop."""
    try:
        db.reference('date_feedback').push({
            'user_id': user_id,
            'target_id': target_id,
            'did_meet': did_meet,
            'vibe_rating': vibe_rating,
            'timestamp': datetime.now(EAT).isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Error saving date feedback: {e}")
        return False

def get_all_feedback() -> list:
    """Fetches real-world date outcomes for analytical reporting."""
    try:
        feedback_dict = db.reference('date_feedback').get()
        return list(feedback_dict.values()) if feedback_dict else [] 
    except Exception as e:
        logger.error(f"Error fetching feedback: {e}")
        return []

def update_user_bio(user_id: str, bio: str) -> bool:
    """Updates the user's bio in their profile."""
    try:
        clear_profiles_cache()
        db.reference(f'profiles/{user_id}').update({'bio': bio})
        return True
    except Exception as e:
        logger.error(f"Error updating bio: {e}")
        return False


# ==========================================
# REAL-TIME CHAT STORAGE & MATCHES
# ==========================================
def get_user_matches(user_id: str) -> list:
    """
    Fetches all active matches for a specific user safely.
    Returns a list of dictionaries containing partner details.
    """
    try:
        # FIX: Fetch all matches and filter in Python to avoid Firebase Index errors
        all_matches = db.reference('matches').get() or {}
        
        result = []
        for match_id, match_data in all_matches.items():
            users_in_match = match_data.get('users', {})
            
            # Check if our current user is part of this match
            if user_id in users_in_match:
                # Find the ID of the person who is NOT the current user
                partner_id = next((uid for uid in users_in_match.keys() if uid != user_id), None)
                
                if partner_id:
                    # Fetch the partner's public profile data
                    partner_profile = db.reference(f'profiles/{partner_id}').get() or {}
                    
                    result.append({
                        'id': partner_id,
                        'name': partner_profile.get('name', 'Unknown Match'),
                        'img': partner_profile.get('img', '/static/img/placeholder.png'),
                        'last_message': match_data.get('last_message', 'Say hi!'),
                        'is_online': partner_profile.get('is_online', False),
                        'is_mutual_match': True 
                    })
                    
        # Optional: Add the AI_COMPANION to everyone's match list by default
        result.append({
            'id': 'AI_COMPANION',
            'name': 'AI Wingman',
            'img': 'https://api.dicebear.com/7.x/bottts/svg?seed=wingman',
            'last_message': 'Need dating advice?',
            'is_online': True,
            'is_mutual_match': False
        })
                
        return result
    except Exception as e:
        logger.error(f"Error fetching user matches for {user_id}: {e}")
        return []
from datetime import datetime, timedelta, timezone

EAT = timezone(timedelta(hours=3))

def cleanup_expired_chats():
    """
    Deletes chat history for dates that happened more than 24 hours ago.
    You can trigger this once a day via a Cron Job or whenever an admin logs in.
    """
    all_bookings = db.reference('bookings').get() or {}
    chats_ref = db.reference('chats')
    
    now = datetime.now(EAT)
    
    for b_id, b_data in all_bookings.items():
        if b_data.get('status') == 'Approved':
            try:
                # Parse the date (Assuming format 'This Friday at 18:00', you might need to adapt your date parser)
                # For simplicity, let's assume you save an actual ISO timestamp when the date starts:
                date_time_str = b_data.get('exact_date_timestamp') 
                if not date_time_str: continue
                
                date_time = datetime.fromisoformat(date_time_str)
                
                # If the date was more than 24 hours ago
                if now > date_time + timedelta(hours=24):
                    user_a = b_data['user_a_id']
                    user_b = b_data['user_b_id']
                    
                    # Generate the chat room ID (usually sorted user IDs joined by an underscore)
                    room_id = f"{min(user_a, user_b)}_{max(user_a, user_b)}"
                    
                    # WIPE THE CHAT
                    chats_ref.child(room_id).delete()
                    
                    # Mark booking as completed/archived so we don't check it again
                    db.reference(f'bookings/{b_id}/status').set('Archived')
                    
            except Exception as e:
                print(f"Error parsing date for booking {b_id}: {e}") 
                  
def save_chat_message(sender_id: str, receiver_id: str, message_text: str, msg_type: str = 'text') -> bool:
    """Permanently saves a chat message."""
    try:
        room_id = "_".join(sorted([sender_id, receiver_id]))
        db.reference(f'chats/{room_id}').push({
            'sender': sender_id,
            'text': message_text,
            'type': msg_type,
            'timestamp': datetime.now(EAT).isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Error saving chat message: {e}")
        return False

def get_chat_history(user_id: str, partner_id: str) -> list:
    """Retrieves the chronological conversation history between two students."""
    try:
        room_id = "_".join(sorted([user_id, partner_id]))
        history = db.reference(f'chats/{room_id}').get()
        return list(history.values()) if history else []
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return []

def terminate_connection(user_id: str, partner_id: str) -> bool:
    """
    Executes a cascading delete to sever a connection between two users.
    Deletes the chat room, wipes mutual swipes, and cancels pending dates.
    """
    try:
        # 1. Delete the Chat Room
        room_id = "_".join(sorted([user_id, partner_id]))
        db.reference(f'chats/{room_id}').delete()
        
        # 2. Query bookings to cancel active dates
        bookings_ref = db.reference('bookings')
        
        # Search where user_id initiated
        initiated_bookings = bookings_ref.order_by_child('user_a_id').equal_to(user_id).get()
        if initiated_bookings:
            for bid, data in initiated_bookings.items():
                if data.get('user_b_id') == partner_id:
                    db.reference(f'bookings/{bid}').delete()
                    
        # Search where partner_id initiated
        received_bookings = bookings_ref.order_by_child('user_a_id').equal_to(partner_id).get()
        if received_bookings:
            for bid, data in received_bookings.items():
                if data.get('user_b_id') == user_id:
                    db.reference(f'bookings/{bid}').delete()
                    
        # 3. Add to 'Blocked' list
        db.reference(f'blocks/{user_id}/{partner_id}').set(True)
        db.reference(f'blocks/{partner_id}/{user_id}').set(True)
        
        logger.info(f"Connection terminated between {user_id} and {partner_id}")
        return True
    except Exception as e:
        logger.error(f"Termination Error: {e}")
        return False

def delete_user_account(user_id: str) -> bool:
    """
    Permanently erases a user and executes a complete cascade wipe 
    of their schedules, bookings, and swipes.
    """
    try:
        clear_profiles_cache()
        # 1. Delete main profile
        db.reference(f'profiles/{user_id}').delete()
        
        # 2. Delete Schedules
        schedules_ref = db.reference('schedules')
        user_schedules = schedules_ref.order_by_child('user_id').equal_to(user_id).get()
        if user_schedules:
            for key in user_schedules:
                db.reference(f'schedules/{key}').delete()

        # 3. Delete Bookings initiated by this user
        bookings_ref = db.reference('bookings')
        user_bookings = bookings_ref.order_by_child('user_a_id').equal_to(user_id).get()
        if user_bookings:
            for key in user_bookings:
                db.reference(f'bookings/{key}').delete()

        # 4. Delete Swipes made by this user
        swipes_ref = db.reference('swipes')
        user_swipes = swipes_ref.order_by_child('user_id').equal_to(user_id).get()
        if user_swipes:
            for key in user_swipes:
                db.reference(f'swipes/{key}').delete()
                    
        logger.info(f"🗑️ Cleaned up and deleted account: {user_id}")
        return True
    except Exception as e:
        logger.error(f"❌ Error deleting account: {e}")
        return False


# ==========================================
# B2B PORTAL: RESTAURANTS, HOTELS & BOOKINGS
# ==========================================

def register_restaurant(owner_name: str, email: str, business_name: str, location: str, conditions: str, images=None) -> str:
    """Registers a new hotel/restaurant into the B2B portal."""
    try:
        new_ref = db.reference('restaurants').push({
            'owner_name': owner_name,
            'email': email,
            'business_name': business_name,
            'location': location,
            'conditions': conditions,
            'images': images or [],
            'subscription_active': False, 
            'subscription_expiry': None,
            'profile_views': 0,
            'join_date': datetime.now(EAT).isoformat()
        })
        return new_ref.key
    except Exception as e:
        logger.error(f"Error registering restaurant: {e}")
        return ""

_restaurants_cache = {}
_restaurants_cache_expiry = None

def get_all_restaurants(active_only: bool = True) -> list:
    """Fetches restaurants with a 30-second cache buffer for high performance."""
    global _restaurants_cache, _restaurants_cache_expiry
    try:
        now = datetime.now()
        cache_key = f"active_{active_only}"
        if cache_key in _restaurants_cache and _restaurants_cache_expiry is not None and now < _restaurants_cache_expiry:
            return _restaurants_cache[cache_key]

        data = db.reference('restaurants').get()
        if not data:
            return []
        
        res = [
            {**rdata, 'id': rid} 
            for rid, rdata in data.items() 
            if not active_only or rdata.get('subscription_active', False)
        ]
        
        # Spotlight Boost: Sort Diamond subscription packages to the top of the feed
        res.sort(key=lambda r: r.get('subscription_package') == 'diamond', reverse=True)
        
        _restaurants_cache[cache_key] = res
        _restaurants_cache_expiry = now + timedelta(seconds=30)
        return res
    except Exception as e:
        logger.error(f"Error fetching restaurants: {e}")
        return []

def increment_restaurant_view(restaurant_id: str) -> None:
    """
    Increments the view count atomically using a Firebase Transaction.
    Prevents race conditions if 100 students view the restaurant at the same time.
    """
    try:
        ref = db.reference(f'restaurants/{restaurant_id}/profile_views')
        ref.transaction(lambda current_views: (current_views or 0) + 1)
    except Exception as e:
        logger.error(f"Error incrementing views: {e}")

def create_date_booking(restaurant_id: str, user_a_id: str, user_b_id: str, date_day: str, date_time: str) -> str:
    """
    Creates a booking request in the B2B portal.
    Returns the generated booking ID.
    """
    try:
        new_ref = db.reference('bookings').push({
            'restaurant_id': restaurant_id,
            'user_a_id': user_a_id,
            'user_b_id': user_b_id,
            'day': date_day,
            'time': date_time,
            'status': 'Pending', 
            'created_at': datetime.now(EAT).isoformat()
        })
        logger.info(f"✅ Booking created successfully for venue {restaurant_id}")
        return new_ref.key
    except Exception as e:
        logger.error(f"❌ Error creating booking: {e}")
        return ""

def get_restaurant_bookings(restaurant_id: str) -> list:
    """Fetches all booking requests for a specific restaurant dashboard."""
    try:
        data = db.reference('bookings').order_by_child('restaurant_id').equal_to(restaurant_id).get()
        if not data:
            return []
            
        return [{**b_data, 'booking_id': bid} for bid, b_data in data.items()]
    except Exception as e:
        logger.error(f"Error fetching bookings: {e}")
        return []

def get_restaurant(restaurant_id: str) -> dict:
    """Fetches a specific restaurant's profile and stats."""
    try:
        data = db.reference(f'restaurants/{restaurant_id}').get()
        if data:
            data['id'] = restaurant_id
        return data or {}
    except Exception as e:
        logger.error(f"Error fetching restaurant: {e}")
        return {}

def update_booking_status(booking_id: str, status: str) -> bool:
    """Updates a booking status safely, appending completed_timestamp if status is 'Completed'."""
    try:
        payload = {'status': status}
        if status == 'Completed':
            payload['completed_timestamp'] = datetime.now(timezone(timedelta(hours=3))).isoformat()
        db.reference(f'bookings/{booking_id}').update(payload)
        logger.info(f"Booking {booking_id} updated to {status}")
        return True
    except Exception as e:
        logger.error(f"Error updating booking status: {e}")
        return False

# ==========================================
# INSTITUTIONS AND CAMPUS MANAGERS
# ==========================================

_institutions_cache = None
_institutions_cache_expiry = None

def get_institutions() -> list:
    """Fetches all dynamically added institutions, with a 1-hour memory cache for instant loads."""
    global _institutions_cache, _institutions_cache_expiry
    try:
        now = datetime.now()
        if _institutions_cache is not None and _institutions_cache_expiry is not None and now < _institutions_cache_expiry:
            return _institutions_cache

        data = db.reference('institutions').get()
        if not data:
            # Seed default institutions
            defaults = [
                {'name': 'Masinde Muliro University (MMUST)', 'type': 'University'},
                {'name': 'University of Nairobi (UoN)', 'type': 'University'},
                {'name': 'Kenyatta University (KU)', 'type': 'University'},
                {'name': 'Jomo Kenyatta University (JKUAT)', 'type': 'University'},
                {'name': 'Moi University', 'type': 'University'},
                {'name': 'Egerton University', 'type': 'University'},
                {'name': 'Strathmore University', 'type': 'University'},
                {'name': 'Kenya Medical Training College (KMTC)', 'type': 'KMTC'},
                {'name': 'Sigalagala National Polytechnic', 'type': 'TVET'},
                {'name': 'Rift Valley Institute of Science and Technology', 'type': 'TVET'},
                {'name': 'General / Other', 'type': 'Other'}
            ]
            for inst in defaults:
                db.reference('institutions').push(inst)
            _institutions_cache = defaults
            _institutions_cache_expiry = now + timedelta(hours=1)
            return defaults
        
        result = [{**inst_data, 'id': iid} for iid, inst_data in data.items()]
        _institutions_cache = result
        _institutions_cache_expiry = now + timedelta(hours=1)
        return result
    except Exception as e:
        logger.error(f"Error fetching institutions: {e}")
        return _institutions_cache if _institutions_cache else []

def add_institution(name: str, inst_type: str) -> bool:
    try:
        db.reference('institutions').push({'name': name, 'type': inst_type})
        return True
    except Exception as e:
        logger.error(f"Error adding institution: {e}")
        return False

def get_campus_managers() -> list:
    """Fetches all campus managers."""
    try:
        data = db.reference('campus_managers').get()
        if not data: return []
        return [{**mgr_data, 'id': mid} for mid, mgr_data in data.items()]
    except Exception as e:
        logger.error(f"Error fetching campus managers: {e}")
        return []

def add_campus_manager(name: str, email: str, institution: str, password_hash: str) -> bool:
    try:
        db.reference('campus_managers').push({
            'name': name,
            'email': email,
            'institution': institution,
            'password_hash': password_hash,
            'referral_code': name.replace(" ", "").upper()[:5] + str(int(datetime.now().timestamp()))[-4:],
            'created_at': datetime.now(EAT).isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Error adding campus manager: {e}")
        return False


# ==========================================
# SPONSORS SYSTEM (v2)
# ==========================================

def create_sponsor_profile(sponsor_id: str, data: dict) -> bool:
    """Saves a new sponsor profile under sponsor_profiles/{sponsor_id}."""
    try:
        data['account_type']  = 'sponsor'
        data['is_verified']   = False
        data['joined_at']     = datetime.now(EAT).isoformat()
        db.reference(f'sponsor_profiles/{sponsor_id}').set(data)
        logger.info(f"✅ Sponsor profile created: {sponsor_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating sponsor profile {sponsor_id}: {e}")
        return False


def get_sponsor_profile(sponsor_id: str) -> dict:
    """Fetches a single sponsor profile."""
    try:
        data = db.reference(f'sponsor_profiles/{sponsor_id}').get()
        if data:
            data['id'] = sponsor_id
        return data or {}
    except Exception as e:
        logger.error(f"Error fetching sponsor {sponsor_id}: {e}")
        return {}


_sponsors_cache = None
_sponsors_cache_expiry = None

def get_all_sponsors(verified_only: bool = False) -> list:
    """Fetches all sponsor profiles with a 30-second cache."""
    global _sponsors_cache, _sponsors_cache_expiry
    try:
        now = datetime.now()
        if _sponsors_cache is not None and _sponsors_cache_expiry and now < _sponsors_cache_expiry:
            data = _sponsors_cache
        else:
            raw = db.reference('sponsor_profiles').get() or {}
            data = [{**v, 'id': k} for k, v in raw.items() if isinstance(v, dict)]
            _sponsors_cache = data
            _sponsors_cache_expiry = now + timedelta(seconds=30)

        if verified_only:
            return [s for s in data if s.get('is_verified')]
        return data
    except Exception as e:
        logger.error(f"Error fetching sponsors: {e}")
        return _sponsors_cache or []


def update_sponsor_profile(sponsor_id: str, updates: dict) -> bool:
    """Partial update to a sponsor profile."""
    try:
        db.reference(f'sponsor_profiles/{sponsor_id}').update(updates)
        global _sponsors_cache
        _sponsors_cache = None  # invalidate cache
        return True
    except Exception as e:
        logger.error(f"Error updating sponsor {sponsor_id}: {e}")
        return False


def get_sponsor_by_email(email: str) -> dict:
    """Finds a sponsor by email (linear scan — sponsors list is small)."""
    try:
        raw = db.reference('sponsor_profiles').get() or {}
        for sid, sdata in raw.items():
            if isinstance(sdata, dict) and sdata.get('email', '').lower() == email.lower():
                return {**sdata, 'id': sid}
        return {}
    except Exception as e:
        logger.error(f"Error finding sponsor by email: {e}")
        return {}


# ------------------------------------------------------------------
# Sponsors Room Student Access
# ------------------------------------------------------------------

def has_sponsors_room_access(user_id: str) -> bool:
    """
    Checks if a student currently has active Sponsors Room access.
    Female students always return True (free access — enforced here).
    """
    try:
        profile = db.reference(f'profiles/{user_id}').get() or {}
        gender = str(profile.get('gender', '')).lower()
        if gender in ('female', 'f'):
            return True  # always free for female students

        access_until_str = profile.get('sponsor_room_access_until')
        if not access_until_str:
            return False
        access_until = datetime.fromisoformat(access_until_str)
        # Make aware if naive
        if access_until.tzinfo is None:
            access_until = access_until.replace(tzinfo=EAT)
        return datetime.now(EAT) < access_until
    except Exception as e:
        logger.error(f"Error checking sponsors room access for {user_id}: {e}")
        return False


def grant_sponsors_room_access(user_id: str, days: int = 30) -> bool:
    """Grants a student Sponsors Room access for N days from now."""
    try:
        expires_at = datetime.now(EAT) + timedelta(days=days)
        db.reference(f'profiles/{user_id}').update({
            'sponsor_room_access_until': expires_at.isoformat()
        })
        clear_profiles_cache()
        logger.info(f"✅ Sponsors Room access granted to {user_id} until {expires_at.date()}")
        return True
    except Exception as e:
        logger.error(f"Error granting sponsors room access: {e}")
        return False


def log_sponsors_room_payment(user_id: str, amount: int, checkout_id: str) -> bool:
    """Logs a Sponsors Room payment for auditing."""
    try:
        db.reference(f'sponsor_room_payments/{user_id}').push({
            'amount': amount,
            'checkout_id': checkout_id,
            'paid_at': datetime.now(EAT).isoformat(),
            'expires_at': (datetime.now(EAT) + timedelta(days=30)).isoformat()
        })
        return True
    except Exception as e:
        logger.error(f"Error logging sponsor room payment: {e}")
        return False
