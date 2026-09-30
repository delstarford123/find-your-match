from app.database import db
import csv
import os

all_profiles = db.reference('profiles').get() or {}

institutions = {}

for uid, data in all_profiles.items():
    if isinstance(data, dict):
        inst = data.get('institution', 'Unknown/None')
        if inst not in institutions:
            institutions[inst] = []
        institutions[inst].append({
            'name': data.get('name', 'N/A'),
            'email': data.get('email', 'N/A'),
            'gender': data.get('gender', 'N/A'),
            'institution': inst
        })

# MMUST first, then others sorted
sorted_insts = sorted(institutions.keys(), key=lambda x: (0 if 'mmust' in x.lower() or 'masinde' in x.lower() else 1, x))

csv_path = os.path.expanduser("~/Desktop/MMUST_Dating_AI_Users_Report.csv")

with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["Institution", "Name", "Email", "Gender"])
    
    for inst in sorted_insts:
        for user in institutions[inst]:
            writer.writerow([user['institution'], user['name'], user['email'], user['gender']])

print(f"Report saved to {csv_path}")
