from app.database import db, initialize_firebase
import random

# Ensure Firebase is connected
initialize_firebase()

def seed_data():
    # 1. DUMMY STUDENTS
    # We give them different majors and Vibe Vectors (Aesthetics)
    dummy_profiles = {
        "SAB_B_01-1111_2023": {
            "name": "Mercy, 20",
            "email": "mercy@student.mmust.ac.ke",
            "bio": "Agriculture student. Love spending time at the MMUST farm. Coffee lover! ☕",
            "img": "https://i.pravatar.cc/400?img=1",
            "vibe_vector": [0.8, 0.1, 0.2, 0.4] # High 'Nature' vibe
        },
        "SIT_B_01-2222_2023": {
            "name": "Brian, 22",
            "email": "brian@student.mmust.ac.ke",
            "bio": "IT Major. Fullstack dev by day, gamer by night. Catch me at the library.",
            "img": "https://i.pravatar.cc/400?img=8",
            "vibe_vector": [0.1, 0.9, 0.3, 0.2] # High 'Tech' vibe
        },
        "SED_B_01-3333_2023": {
            "name": "Stacy, 21",
            "email": "stacy@student.mmust.ac.ke",
            "bio": "Education student. I love poetry and quiet walks at the Kakamega Forest gate. 🌲",
            "img": "https://i.pravatar.cc/400?img=5",
            "vibe_vector": [0.7, 0.2, 0.1, 0.5]
        },
        "SBC_B_01-4444_2023": {
            "name": "David, 23",
            "email": "david@student.mmust.ac.ke",
            "bio": "Business Admin. Looking for someone to grab lunch with at Savoury Classic.",
            "img": "https://i.pravatar.cc/400?img=12",
            "vibe_vector": [0.3, 0.4, 0.9, 0.1]
        },
        "SNU_B_01-5555_2023": {
            "name": "Faith, 20",
            "email": "faith@student.mmust.ac.ke",
            "bio": "Nursing. Busy labs but I always have time for a good chat. AI match me! ✨",
            "img": "https://i.pravatar.cc/400?img=10",
            "vibe_vector": [0.4, 0.3, 0.2, 0.8]
        }
    }

    # 2. DUMMY SCHEDULES
    # We create overlapping times so the "Schedule Match" logic triggers
    dummy_schedules = [
        {"user_id": "SAB_B_01-1111_2023", "day_of_week": "Tuesday", "start_time": "14:00", "end_time": "16:00"},
        {"user_id": "SIT_B_01-2222_2023", "day_of_week": "Tuesday", "start_time": "15:00", "end_time": "17:00"},
        {"user_id": "SED_B_01-3333_2023", "day_of_week": "Monday", "start_time": "10:00", "end_time": "12:00"},
        {"user_id": "SBC_B_01-4444_2023", "day_of_week": "Wednesday", "start_time": "12:00", "end_time": "14:00"},
        {"user_id": "SNU_B_01-5555_2023", "day_of_week": "Tuesday", "start_time": "14:30", "end_time": "16:30"}
    ]

    print("🌱 Seeding MMUST Profiles...")
    db.reference('profiles').update(dummy_profiles)
    
    print("🕒 Seeding MMUST Schedules...")
    sched_ref = db.reference('schedules')
    for s in dummy_schedules:
        sched_ref.push(s)

    print("✅ Database successfully populated with 5 test students!")

if __name__ == "__main__":
    seed_data()