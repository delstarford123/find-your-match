import os
import sys
import time
from dotenv import load_dotenv

# Load env before anything else so credentials are found!
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from database import get_all_profiles, initialize_firebase
from email_service import send_system_update_email

def run_system_update_campaign():
    print("🚀 Starting System Update Campaign...")
    initialize_firebase()
    
    all_profiles_list = get_all_profiles()
    
    if not all_profiles_list:
        print("No profiles found in database.")
        return
        
    success_count = 0
    fail_count = 0
    
    for profile in all_profiles_list:
        email = profile.get('email')
        name = profile.get('name', 'User')
        
        if not email:
            continue
            
        print(f"Sending to {name} ({email})...")
        
        try:
            success = send_system_update_email(email, name)
            if success:
                success_count += 1
                print("   ✅ Success")
            else:
                fail_count += 1
                print("   ❌ Failed")
                
            # Sleep to respect email provider rate limits
            time.sleep(1) 
        except Exception as e:
            fail_count += 1
            print(f"   ❌ Error: {e}")
            
    print("-" * 30)
    print("🎉 Campaign Complete!")
    print(f"Total Sent: {success_count}")
    print(f"Total Failed: {fail_count}")

if __name__ == "__main__":
    run_system_update_campaign()
