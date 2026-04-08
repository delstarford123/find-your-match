import os
import sys
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Define East Africa Time (UTC+3) for accurate Kenyan timestamps
EAT = timezone(timedelta(hours=3))

# ==========================================
# 1. CONNECT TO FIREBASE
# ==========================================
CREDENTIALS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'firebase_key.json'))
DATABASE_URL = os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")

def initialize_firebase():
    if not firebase_admin._apps:
        try:
            if not os.path.exists(CREDENTIALS_PATH):
                print(f"❌ ERROR: Cannot find firebase_key.json at {CREDENTIALS_PATH}")
                print("Make sure the key file is in the same folder as this script.")
                sys.exit(1)
                
            cred = credentials.Certificate(CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred, {'databaseURL': DATABASE_URL})
            print("🔗 Successfully connected to Firebase database.")
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            sys.exit(1)

# ==========================================
# 2. THE UNLOCK FUNCTION (BY EMAIL)
# ==========================================
def grant_vip_access(email_address):
    """Searches for a user by email and grants them a 30-day VIP pass."""
    email_clean = email_address.strip().lower()
    print(f"\n🔍 Searching database for email: {email_clean}...")
    
    try:
        profiles_ref = db.reference('profiles')
        # Search the database for the matching EMAIL
        matching_users = profiles_ref.order_by_child('email').equal_to(email_clean).get()
        
        if matching_users:
            for uid, user_data in matching_users.items():
                name = user_data.get('name', 'Unknown User')
                
                # Calculate expiry date (30 days from right now in EAT)
                now_eat = datetime.now(EAT)
                expiry_date = (now_eat + timedelta(days=30)).isoformat()
                
                # Flip the switch and add the expiry date!
                db.reference(f'profiles/{uid}').update({
                    'is_paid': True,
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': 'GOD_MODE_VIP_PASS' # So you know how they got it
                })
                
                print(f"\n👤 Found User: {name} (ID: {uid})")
                print(f"✅ SUCCESS: VIP Access Granted!")
                print(f"📅 Pass expires on: {expiry_date[:10]}")
        else:
            print(f"\n❌ ERROR: Could not find any account registered with {email_clean}.")
            print("Make sure you typed the exact email they used to sign up.")
            
    except Exception as e:
        print(f"\n❌ Database Error: {e}")

# ==========================================
# 3. RUN THE SCRIPT
# ==========================================
if __name__ == "__main__":
    print("\n======================================")
    print(" 🛠️  FIND YOUR MATCH - VIP UNLOCK TOOL ")
    print("======================================")
    
    initialize_firebase()
    
    while True:
        target_email = input("\nEnter the EMAIL ADDRESS to unlock (or type 'exit' to quit): ").strip()
        
        if target_email.lower() in ['exit', 'quit', 'q']:
            print("Exiting tool. Goodbye!")
            break
        elif target_email:
            grant_vip_access(target_email)
        else:
            print("Please enter a valid email address.")