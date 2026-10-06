import os
import sys
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
import uuid
from werkzeug.security import generate_password_hash

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
def grant_vip_access(email_address, package='premium'):
    """Searches for a user or sponsor by email and grants them VIP access."""
    email_clean = email_address.strip().lower()
    print(f"\n🔍 Searching database for email: {email_clean}...")
    
    try:
        # 1. Search Student Profiles
        profiles_ref = db.reference('profiles')
        matching_users = profiles_ref.order_by_child('email').equal_to(email_clean).get()
        
        if matching_users:
            for uid, user_data in matching_users.items():
                name = user_data.get('name', 'Unknown User')
                
                # Calculate expiry date (30 days from right now in EAT)
                now_eat = datetime.now(EAT)
                expiry_date = (now_eat + timedelta(days=30)).isoformat()
                
                # Flip the switch and add the expiry date & subscription package!
                db.reference(f'profiles/{uid}').update({
                    'is_paid': True,
                    'subscription_package': package,
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': f'GOD_MODE_{package.upper()}_PASS'
                })
                
                print(f"\n👤 Found Student: {name} (ID: {uid})")
                print(f"✅ SUCCESS: {package.upper()} VIP Access Granted!")
                print(f"📅 Pass expires on: {expiry_date[:10]}")
            return

        # 2. Search Sponsor Profiles
        sponsors_ref = db.reference('sponsor_profiles')
        matching_sponsors = sponsors_ref.order_by_child('email').equal_to(email_clean).get()

        if matching_sponsors:
            for sid, sponsor_data in matching_sponsors.items():
                name = sponsor_data.get('name', 'Unknown Sponsor')
                
                now_eat = datetime.now(EAT)
                expiry_date = (now_eat + timedelta(days=3650)).isoformat() # Lifetime VIP
                
                db.reference(f'sponsor_profiles/{sid}').update({
                    'is_active': True,
                    'is_verified': True,
                    'subscription_package': 'sponsor',
                    'subscription_expiry': expiry_date,
                    'last_payment_receipt': 'GOD_MODE_SPONSOR_PASS'
                })
                
                print(f"\n🌟 Found Sponsor: {name} (ID: {sid})")
                print(f"✅ SUCCESS: Sponsor Access Granted!")
            return

        # 3. Not Found -> Ask to Create Sponsor
        print(f"\n❌ Could not find any account registered with {email_clean}.")
        print("Note: Sponsors are NOT saved to the database until they pay.")
        create_new = input("Would you like to CREATE a NEW Sponsor account and bypass payment? (y/n): ").strip().lower()
        
        if create_new == 'y':
            create_sponsor_bypass(email_clean)
        else:
            print("Operation cancelled. Make sure you typed the exact email they used to sign up.")
            
    except Exception as e:
        print(f"\n❌ Database Error: {e}")

def create_sponsor_bypass(email):
    print(f"\n--- CREATING NEW SPONSOR ---")
    name = input("Enter Full Name: ").strip()
    phone = input("Enter Phone Number (e.g., 0712345678): ").strip()
    gender = input("Enter Gender (male/female): ").strip().lower()
    password = input("Enter a temporary password for them: ").strip()
    
    sponsor_id = f"spon_{uuid.uuid4().hex[:16]}"
    now_eat = datetime.now(EAT)
    expiry_date = (now_eat + timedelta(days=3650)).isoformat()
    
    sponsor_data = {
        'id': sponsor_id,
        'name': name,
        'email': email,
        'phone': phone,
        'password_hash': generate_password_hash(password),
        'gender': gender,
        'is_active': True,
        'is_verified': True,
        'subscription_package': 'sponsor',
        'subscription_expiry': expiry_date,
        'last_payment_receipt': 'GOD_MODE_SPONSOR_PASS',
        'created_at': now_eat.isoformat()
    }
    
    try:
        db.reference(f'sponsor_profiles/{sponsor_id}').set(sponsor_data)
        print(f"\n✅ SUCCESS: Sponsor account created & payment bypassed!")
        print(f"They can now log in at /sponsor/login with:")
        print(f"Email: {email}")
        print(f"Password: {password}")
    except Exception as e:
        print(f"❌ Failed to save sponsor: {e}")

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
            grant_vip_access(target_email, 'premium')
        else:
            print("Please enter a valid email address.")