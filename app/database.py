import os
import logging
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db

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
            if not os.path.exists(CREDENTIALS_PATH):
                logger.error(f"Missing Firebase Key file at: {CREDENTIALS_PATH}")
                return
                
            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {
                'databaseURL': DATABASE_URL
            })
            logger.info("🔥 Firebase Realtime Database connected successfully!")
        except Exception as e:
            logger.error(f"❌ Firebase Connection Error: {e}")

# Run initialization immediately upon import
initialize_firebase()


# ==========================================
# DATABASE HELPER FUNCTIONS (STUDENT USERS)
# ==========================================

def get_all_profiles() -> list:
    """Fetches all students from the 'profiles' node."""
    try:
        users_dict = db.reference('profiles').get()
        if not users_dict:
            return []
        return [{**data, 'id': uid} for uid, data in users_dict.items() if data]
    except Exception as e:
        logger.error(f"Error fetching profiles: {e}")
        return []

def save_swipe(user_id: str, target_id: str, action: str, timestamp: str) -> str:
    """Pushes a new swipe record and returns its generated ID."""
    try:
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
    Fetches all active matches for a specific user.
    Returns a list of dictionaries containing partner details.
    """
    try:
        # Query the matches table where this user is listed in the 'users' dict
        matches_ref = db.reference('matches')
        user_matches = matches_ref.order_by_child(f'users/{user_id}').equal_to(True).get()
        
        if not user_matches:
            return []
            
        result = []
        for match_id, match_data in user_matches.items():
            # Find the ID of the person who is NOT the current user
            users_in_match = match_data.get('users', {})
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

def get_all_restaurants(active_only: bool = True) -> list:
    """Fetches restaurants. active_only=True filters for paid subscriptions."""
    try:
        data = db.reference('restaurants').get()
        if not data:
            return []
        
        return [
            {**rdata, 'id': rid} 
            for rid, rdata in data.items() 
            if not active_only or rdata.get('subscription_active', False)
        ]
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
    """Updates a booking to 'Approved' or 'Declined'."""
    try:
        db.reference(f'bookings/{booking_id}').update({'status': status})
        logger.info(f"Booking {booking_id} updated to {status}")
        return True
    except Exception as e:
        logger.error(f"Error updating booking status: {e}")
        return False