import sys
import time

# Import your existing Firebase connection from your app
try:
    from app.database import db
except ImportError as e:
    print("❌ ERROR: Could not import your database connection.")
    print("Make sure you are running this script from the root folder (mmust-dating-ai).")
    print(f"Details: {e}")
    sys.exit(1)

def purge_unverified_users():
    print("\n🔍 Scanning Firebase for unverified accounts...")
    time.sleep(1) # Small pause for readability
    
    profiles_ref = db.reference('profiles')
    all_profiles = profiles_ref.get()

    if not all_profiles:
        print("✅ No profiles found in the database. Exiting.")
        return

    unverified_uids = []
    
    # Loop through the database and find unverified users
    for uid, user_data in all_profiles.items():
        if not isinstance(user_data, dict):
            continue
        
        is_verified = user_data.get('is_verified', False)
        
        if not is_verified:
            unverified_uids.append(uid)

    total_unverified = len(unverified_uids)

    if total_unverified == 0:
        print("✅ Database is clean! 0 unverified accounts found.")
        return

    # SAFETY CHECK
    print(f"\n⚠️ FOUND {total_unverified} UNVERIFIED ACCOUNTS.")
    print("These accounts will be PERMANENTLY deleted from Firebase.")
    
    confirm = input("\nType 'YES' (all caps) to confirm deletion: ")
    
    if confirm == 'YES':
        print(f"\n🗑️ Initiating purge of {total_unverified} accounts...\n")
        deleted_count = 0
        
        for uid in unverified_uids:
            try:
                # Delete the user profile
                db.reference(f'profiles/{uid}').delete()
                
                # IMPORTANT: Delete their schedules and swipes to keep the DB clean!
                db.reference(f'schedules/{uid}').delete()
                
                deleted_count += 1
                print(f"  [-] Wiped user: {uid}")
            except Exception as e:
                print(f"  [!] Failed to delete {uid}: {e}")
        
        print(f"\n✅ Purge complete! Successfully deleted {deleted_count} unverified accounts.")
    else:
        print("\n🛑 Aborted. No accounts were deleted.")

if __name__ == '__main__':
    purge_unverified_users()