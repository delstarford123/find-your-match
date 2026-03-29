import os
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# 1. CONNECT TO FIREBASE
# ==========================================
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'firebase_key.json'))
DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")

def initialize_firebase():
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("🔗 Connected to Firebase database.")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            exit(1)

# ==========================================
# 2. THE UNLOCK FUNCTION (BY EMAIL)
# ==========================================
def grant_vip_access(email_address):
    """Searches for a user by email and sets is_paid to True."""
    email_clean = email_address.strip().lower()
    print(f"\n🔍 Searching for account with email: {email_clean}...")
    
    try:
        profiles_ref = db.reference('profiles')
        # Search the database for the matching EMAIL
        matching_users = profiles_ref.order_by_child('email').equal_to(email_clean).get()
        
        if matching_users:
            for uid, user_data in matching_users.items():
                name = user_data.get('name', 'Unknown User')
                
                # Flip the switch!
                db.reference(f'profiles/{uid}').update({'is_paid': True})
                
                print(f"👤 Found User: {name} (ID: {uid})")
                print(f"✅ SUCCESS: Account bypassed paywall! 'is_paid' is now True.")
        else:
            print(f"❌ ERROR: Could not find any account registered with {email_clean}.")
            print("Make sure you typed the exact email shown in your database snippet.")
            
    except Exception as e:
        print(f"Database error: {e}")

# ==========================================
# 3. RUN THE SCRIPT
# ==========================================
if __name__ == "__main__":
    print("======================================")
    print(" 🛠️ FIND YOUR MATCH - VIP UNLOCK TOOL ")
    print("======================================")
    
    initialize_firebase()
    
    target_email = input("\nEnter the EMAIL ADDRESS to unlock: ")
    
    if target_email.strip():
        grant_vip_access(target_email)
    else:
        print("Operation cancelled.")