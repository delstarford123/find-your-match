import os
import firebase_admin
from firebase_admin import credentials, db, auth
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==========================================
# 1. INITIALIZE FIREBASE
# ==========================================
def initialize_firebase():
    """Initializes the Firebase Admin SDK."""
    if not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_CREDENTIALS", "firebase_key.json")
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {
                'databaseURL': os.getenv("FIREBASE_DB_URL")
            })
            print("✅ Firebase connected successfully.\n")
        except Exception as e:
            print(f"❌ Failed to connect to Firebase: {e}")
            print("Ensure 'firebase_key.json' is in the folder and 'FIREBASE_DB_URL' is set correctly.")
            exit(1)

# ==========================================
# 2. CATEGORIZE USERS
# ==========================================
def get_categorized_users():
    """Fetches users from Auth & RTDB and categorizes them."""
    print("Fetching users from Firebase... Please wait.")
    
    auth_users = {user.uid: user for user in auth.list_users().iterate_all()}
    rtdb_profiles = db.reference('profiles').get() or {}

    all_uids = set(auth_users.keys()).union(set(rtdb_profiles.keys()))

    all_users = []
    unverified = []
    unpaid = []
    premium = []

    for uid in all_uids:
        auth_user = auth_users.get(uid)
        profile = rtdb_profiles.get(uid, {})
        
        if not isinstance(profile, dict):
            profile = {}
            
        email = profile.get('email') or (auth_user.email if auth_user else "No Email (RTDB Only)")
        name = profile.get('name') or (auth_user.display_name if auth_user else "Unknown Student")
        is_paid = profile.get('is_paid', False)
        
        user_data = {
            'uid': uid,
            'email': email,
            'name': name
        }
        
        # Add everyone to the Total list
        all_users.append(user_data)

        # Categorize into sub-levels
        if not auth_user or not getattr(auth_user, 'email_verified', False):
            unverified.append(user_data)
        elif not is_paid:
            unpaid.append(user_data)
        else:
            premium.append(user_data)

    return all_users, unverified, unpaid, premium

# ==========================================
# 3. DEEP CLEAN DELETION LOGIC
# ==========================================
def delete_user_completely(uid):
    """Wipes the user from Authentication and every node in the Realtime Database."""
    try:
        # 1. Delete from Firebase Authentication
        try:
            auth.delete_user(uid)
        except firebase_admin.auth.AuthError:
            pass # User might only exist in the Realtime Database
            
        # 2. Direct Node Deletions
        db.reference(f'profiles/{uid}').delete()
        db.reference(f'schedules/{uid}').delete()
        db.reference(f'call_reviews/{uid}').delete()

        # 3. Clean up Matches
        all_matches = db.reference('matches').get() or {}
        for match_id in all_matches.keys():
            if uid in str(match_id):
                db.reference(f'matches/{match_id}').delete()

        # 4. Clean up Swipes
        swipes_ref = db.reference('swipes')
        swipes_by_user = swipes_ref.order_by_child('user_id').equal_to(uid).get()
        if swipes_by_user:
            for key in swipes_by_user: swipes_ref.child(key).delete()
            
        swipes_by_target = swipes_ref.order_by_child('target_id').equal_to(uid).get()
        if swipes_by_target:
            for key in swipes_by_target: swipes_ref.child(key).delete()

        # 5. Clean up Bookings
        bookings_ref = db.reference('bookings')
        bookings_a = bookings_ref.order_by_child('user_a_id').equal_to(uid).get()
        if bookings_a:
            for key in bookings_a: bookings_ref.child(key).delete()
            
        bookings_b = bookings_ref.order_by_child('user_b_id').equal_to(uid).get()
        if bookings_b:
            for key in bookings_b: bookings_ref.child(key).delete()

        return True
    except Exception as e:
        print(f"   ❌ Error deleting footprint for {uid}: {e}")
        return False

# ==========================================
# 4. INTERACTIVE CLI
# ==========================================
def main():
    initialize_firebase()
    
    while True:
        all_users, unverified, unpaid, premium = get_categorized_users()

        print("\n" + "="*50)
        print(" 🗑️  MMUST DATING - DEEP CLEAN DELETION TOOL")
        print("="*50)
        print(f"1. All Users (Total Database) [{len(all_users)}]")
        print(f"2. Unverified Users [{len(unverified)}]")
        print(f"3. Verified (Unpaid) Users [{len(unpaid)}]")
        print(f"4. Premium Users [{len(premium)}]")
        print("5. Exit")
        print("="*50)
        
        choice = input("Select a level to view/delete users (1-5): ").strip()
        
        if choice == '5':
            print("Exiting tool. Goodbye!")
            break
            
        if choice == '1':
            selected_group = all_users
            level_name = "All Database"
        elif choice == '2':
            selected_group = unverified
            level_name = "Unverified"
        elif choice == '3':
            selected_group = unpaid
            level_name = "Verified (Unpaid)"
        elif choice == '4':
            selected_group = premium
            level_name = "Premium"
        else:
            print("⚠️ Invalid choice. Please try again.")
            continue

        if not selected_group:
            print(f"\n✅ There are no {level_name} users to delete.")
            continue

        print(f"\n--- {level_name.upper()} USERS ---")
        for idx, user in enumerate(selected_group, 1):
            print(f"[{idx}] Name: {user['name']} | Email: {user['email']} | UID: {user['uid']}")
        
        print("\nEnter the numbers of the users to delete, separated by commas (e.g., 1,3,4).")
        print("Type 'ALL' to delete everyone in this category, or '0' to cancel.")
        
        target = input("\nYour selection: ").strip().lower()
        
        if target == '0' or target == 'cancel':
            continue
            
        users_to_delete = []
        
        if target == 'all':
            confirm = input(f"⚠️  WARNING: Are you sure you want to completely wipe ALL {len(selected_group)} {level_name} users from the system? (yes/no): ").strip().lower()
            if confirm == 'yes':
                users_to_delete = selected_group.copy()
            else:
                print("Action cancelled.")
                continue
        else:
            try:
                indices = [int(x.strip()) - 1 for x in target.split(',')]
                for i in indices:
                    if 0 <= i < len(selected_group):
                        users_to_delete.append(selected_group[i])
            except ValueError:
                print("⚠️ Invalid input format. Returning to menu.")
                continue

        if not users_to_delete:
            continue

        print("\nStarting deep clean deletion process...")
        success_count = 0
        for user in users_to_delete:
            print(f" -> Wiping {user['name']} ({user['email']})...", end="")
            if delete_user_completely(user['uid']):
                print(" SUCCESS")
                success_count += 1
            
        print(f"\n✅ Deep clean complete. Successfully removed {success_count} user(s).")
        print("Refreshing database counts...\n")

if __name__ == "__main__":
    main()