import os
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime

# Load env variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Init Firebase
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase_key.json"))
        firebase_admin.initialize_app(cred, {
            'databaseURL': os.getenv("FIREBASE_DB_URL", "https://mmust-dating-site-default-rtdb.firebaseio.com/")
        })
    except Exception as e:
        print(f"Failed to init Firebase: {e}")

institutions_data = {
    "University": [
        "University of Nairobi (UoN)", "Kenyatta University (KU)", "Moi University (MU)",
        "Egerton University (EU)", "Jomo Kenyatta University of Agriculture and Technology (JKUAT)",
        "Maseno University (MSU)", "Masinde Muliro University of Science and Technology (MMUST)",
        "Dedan Kimathi University of Technology (DeKUT)", "Chuka University (CU)",
        "Technical University of Kenya (TU-K)", "Technical University of Mombasa (TUM)",
        "Pwani University (PU)", "Kisii University", "University of Eldoret (UoE)",
        "Masai Mara University", "Machakos University", "Laikipia University",
        "South Eastern Kenya University (SEKU)", "Meru University of Science and Technology (MUST)",
        "Multimedia University of Kenya (MMU)", "University of Kabianga (UoK)",
        "Karatina University", "Kibabii University", "Rongo University",
        "Co-operative University of Kenya", "Taita Taveta University (TTU)",
        "Murang'a University of Technology", "University of Embu",
        "Garissa University", "Alupe University", "Kaimosi Friends University",
        "Tom Mboya University", "Tharaka University", "Bomet University",
        "Koitalel Samoei University", "Strathmore University", "Mount Kenya University (MKU)",
        "United States International University Africa (USIU)", "Catholic University of Eastern Africa (CUEA)",
        "Daystar University", "Zetech University", "KCA University",
        "Kenya Methodist University (KeMU)", "Kabarak University", "Africa Nazarene University",
        "Pan Africa Christian University", "Scott Christian University",
        "Great Lakes University of Kisumu", "Gretsa University", "Riara University",
        "Lukenya University", "Umma University", "Amref International University",
        "Management University of Africa"
    ],
    "National Polytechnic": [
        "The Nairobi National Polytechnic", "The Kisumu National Polytechnic",
        "The Eldoret National Polytechnic", "The Nyeri National Polytechnic",
        "The Kabete National Polytechnic", "The Kenya Coast National Polytechnic",
        "The Meru National Polytechnic", "The Kisii National Polytechnic",
        "The Kitale National Polytechnic", "The Sigalagala National Polytechnic",
        "The North Eastern Province National Polytechnic", "The Nkabune National Polytechnic",
        "The Rift Valley National Polytechnic", "The Nyandarua National Polytechnic",
        "The Baringo National Polytechnic", "The Wote National Polytechnic",
        "The Masai Technical Training Institute (National Polytechnic)"
    ],
    "Polytechnic": [
        "Mombasa Polytechnic", "Kiambu Institute of Science and Technology (Polytechnic level)",
        "Bumbe Technical Training Institute (Polytechnic)", "Bondo Technical Training Institute"
    ],
    "KMTC": [
        "KMTC Nairobi", "KMTC Mombasa", "KMTC Kisumu", "KMTC Nakuru", "KMTC Machakos",
        "KMTC Eldoret", "KMTC Kakamega", "KMTC Nyeri", "KMTC Garissa", "KMTC Embu",
        "KMTC Thika", "KMTC Kilifi", "KMTC Bungoma", "KMTC Meru", "KMTC Homabay",
        "KMTC Port Reitz", "KMTC Bomet", "KMTC Kisii", "KMTC Voi", "KMTC Webuye",
        "KMTC Siaya", "KMTC Kapenguria", "KMTC Kabarnet", "KMTC Kitui", "KMTC Mutomo",
        "KMTC Lodwar", "KMTC Kuria", "KMTC Rachuonyo", "KMTC Nyahururu", "KMTC Murang'a"
    ],
    "TTI": [
        "Thika Technical Training Institute", "Rift Valley Technical Training Institute (RVTTI)",
        "Kabete Technical Training Institute", "Kaiboi Technical Training Institute",
        "Machakos Technical Training Institute", "Nairobi Technical Training Institute",
        "Mawego Technical Training Institute", "Kisiwa Technical Training Institute",
        "Rift Valley Institute of Science and Technology (RVIST)", "Miteero Technical Training Institute",
        "Wanga Technical Training Institute", "Bondo Technical Training Institute",
        "Ekerubo Gietai Technical Training Institute", "Bureti Technical Training Institute",
        "Kericho Technical Training Institute"
    ],
    "TTC": [
        "Kaimosi Teachers Training College", "Asumbi Teachers Training College",
        "Machakos Teachers Training College", "Shanzu Teachers Training College",
        "Kigari Teachers Training College", "Mosoriot Teachers Training College",
        "Eregi Teachers Training College", "Baringo Teachers Training College",
        "Tambach Teachers Training College", "Kamwenja Teachers Training College",
        "Meru Teachers Training College", "Murang'a Teachers Training College"
    ],
    "College": [
        "Kenya School of Law (KSL)", "Kenya School of Government (KSG)",
        "Kenya Institute of Management (KIM)", "Kenya Water Institute (KEWI)",
        "Kenya School of Revenue Administration (KESRA)", "Utalii College",
        "Kenya Institute of Mass Communication (KIMC)", "East African School of Aviation",
        "Railway Training Institute", "Bandari Maritime Academy"
    ],
    "Institute of Technology": [
        "Kiambu Institute of Science and Technology (KIST)",
        "Ramogi Institute of Advanced Technology (RIAT)",
        "Sang'alo Institute of Science and Technology",
        "Rift Valley Institute of Science and Technology (RVIST)",
        "Coast Institute of Technology", "Mendeo Institute of Technology"
    ]
}

def seed_db():
    ref = db.reference('institutions')
    
    # First get existing
    existing = ref.get() or {}
    existing_names = set(v.get('name') for v in existing.values() if isinstance(v, dict))
    
    count = 0
    now = datetime.now().isoformat()
    
    for inst_type, names in institutions_data.items():
        for name in names:
            if name not in existing_names:
                ref.push({
                    'name': name,
                    'type': inst_type,
                    'created_at': now
                })
                existing_names.add(name)
                count += 1
                
    print(f"Successfully seeded {count} new institutions across {len(institutions_data)} categories.")

if __name__ == "__main__":
    seed_db()
