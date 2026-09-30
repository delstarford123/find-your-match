from app.database import db
import json

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
            'gender': data.get('gender', 'N/A')
        })

# MMUST first, then others sorted
sorted_insts = sorted(institutions.keys(), key=lambda x: (0 if 'mmust' in x.lower() or 'masinde' in x.lower() else 1, x))

results = []
for inst in sorted_insts:
    results.append(f"=== {inst} ({len(institutions[inst])} users) ===")
    for user in institutions[inst]:
        results.append(f"  - {user['name']} | {user['email']} | {user['gender']}")
    results.append("")

with open("scratch/users_by_inst.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))

print("Done. Saved to scratch/users_by_inst.txt")
