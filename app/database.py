import os
import logging
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, db

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. SETUP FIREBASE CONNECTION
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../firebase_key.json'))

# Fetch from environment variables for security, fallback to hardcoded string
DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")

def initialize_firebase():
    """Initializes the Firebase Admin SDK to talk to your cloud database."""
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

# Run initialization immediately
initialize_firebase()


# ==========================================
# DATABASE HELPER FUNCTIONS (USERS)
# ==========================================

def get_all_profiles() -> list:
    """Fetches all students from the 'profiles' node in Firebase."""
    try:
        users_dict = db.reference('profiles').get()
        if not users_dict:
            return []
            
        return [{**data, 'id': uid} for uid, data in users_dict.items() if data]
    except Exception as e:
        logger.error(f"Error fetching profiles: {e}")
        return []

def save_swipe(user_id: str, target_id: str, action: str, timestamp: str):
    """Pushes a new swipe record to the 'swipes' node."""
    try:
        db.reference('swipes').push({
            'user_id': user_id,
            'target_id': target_id,
            'action': action,
            'timestamp': timestamp
        })
    except Exception as e:
        logger.error(f"Error saving swipe: {e}")

def get_all_swipes() -> list:
    """Fetches all swipes for the Collaborative Filtering model."""
    try:
        swipes_dict = db.reference('swipes').get()
        return list(swipes_dict.values()) if swipes_dict else []
    except Exception as e:
        logger.error(f"Error fetching swipes: {e}")
        return []

def save_schedule(user_id: str, day_of_week: str, start_time: str, end_time: str):
    """Pushes a free-time block to the user's schedule."""
    try:
        db.reference('schedules').push({
            'user_id': user_id,
            'day_of_week': day_of_week,
            'start_time': start_time,
            'end_time': end_time
        })
        logger.info(f"✅ Saved schedule for {user_id}")
    except Exception as e:
        logger.error(f"Error saving schedule: {e}")

def get_all_schedules() -> list:
    """Fetches all schedules for the AI Matcher."""
    try:
        schedules_dict = db.reference('schedules').get()
        return list(schedules_dict.values()) if schedules_dict else []
    except Exception as e:
        logger.error(f"Error fetching schedules: {e}")
        return []

def save_date_feedback(user_id: str, target_id: str, did_meet: bool, vibe_rating: str):
    """Saves post-date feedback for the 'Holy Grail' ML loop."""
    try:
        db.reference('date_feedback').push({
            'user_id': user_id,
            'target_id': target_id,
            'did_meet': did_meet,
            'vibe_rating': vibe_rating,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving date feedback: {e}")

def get_all_feedback() -> list:
    """Fetches real-world date outcomes."""
    try:
        feedback_dict = db.reference('date_feedback').get()
        return list(feedback_dict.values()) if feedback_dict else [] 
    except Exception as e:
        logger.error(f"Error fetching feedback: {e}")
        return []

def update_user_bio(user_id: str, bio: str):
    """Updates the user's bio in their profile."""
    try:
        db.reference(f'profiles/{user_id}').update({'bio': bio})
        logger.info(f"✅ Bio updated for {user_id}")
    except Exception as e:
        logger.error(f"Error updating bio: {e}")

# ==========================================
# REAL-TIME CHAT STORAGE
# ==========================================

def save_chat_message(sender_id: str, receiver_id: str, message_text: str, msg_type: str = 'text'):
    """Permanently saves a chat message so it can be loaded later."""
    try:
        room_id = "_".join(sorted([sender_id, receiver_id]))
        db.reference(f'chats/{room_id}').push({
            'sender': sender_id,
            'text': message_text,
            'type': msg_type,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error saving chat message: {e}")

def get_chat_history(user_id: str, partner_id: str) -> list:
    """Retrieves the conversation history between two students."""
    try:
        room_id = "_".join(sorted([user_id, partner_id]))
        history = db.reference(f'chats/{room_id}').get()
        return list(history.values()) if history else []
    except Exception as e:
        logger.error(f"Error fetching chat history: {e}")
        return []

def delete_user_account(user_id: str) -> bool:
    """Permanently erases a user and their specific schedule blocks."""
    try:
        # 1. Delete the main profile
        db.reference(f'profiles/{user_id}').delete()
        
        # 2. PERFORMANCE FIX: Query ONLY this user's schedules, instead of downloading all of them
        schedules_ref = db.reference('schedules')
        user_schedules = schedules_ref.order_by_child('user_id').equal_to(user_id).get()
        
        if user_schedules:
            for key in user_schedules:
                db.reference(f'schedules/{key}').delete()
                    
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
            'join_date': datetime.now().isoformat()
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

def increment_restaurant_view(restaurant_id: str):
    """Increments the view count when a dating user clicks to view the hotel."""
    try:
        ref = db.reference(f'restaurants/{restaurant_id}/profile_views')
        current_views = ref.get() or 0
        ref.set(current_views + 1)
    except Exception as e:
        logger.error(f"Error incrementing views: {e}")

def create_date_booking(restaurant_id: str, user_a_id: str, user_b_id: str, date_day: str, date_time: str):
    """Creates a booking request for the restaurant owner to approve."""
    try:
        db.reference('bookings').push({
            'restaurant_id': restaurant_id,
            'user_a_id': user_a_id,
            'user_b_id': user_b_id,
            'day': date_day,
            'time': date_time,
            'status': 'Pending', 
            'created_at': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error creating booking: {e}")

def get_restaurant_bookings(restaurant_id: str) -> list:
    """Fetches all booking requests for a specific restaurant dashboard."""
    try:
        # PERFORMANCE FIX: Query database directly for this specific restaurant ID
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

def update_booking_status(booking_id: str, status: str):
    """Updates a booking to 'Approved' or 'Declined'."""
    try:
        db.reference(f'bookings/{booking_id}').update({'status': status})
        logger.info(f"Booking {booking_id} updated to {status}")
    except Exception as e:
        logger.error(f"Error updating booking status: {e}")

def terminate_connection(user_id: str, partner_id: str) -> bool:
    """
    Executes a cascading delete to sever a connection between two users.
    Deletes the chat room, wipes mutual swipes, and cancels pending dates.
    """
    try:
        # 1. Delete the Chat Room
        room_id = "_".join(sorted([user_id, partner_id]))
        db.reference(f'chats/{room_id}').delete()
        
        # 2. PERFORMANCE FIX: Query bookings for user_a_id to prevent downloading all bookings
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