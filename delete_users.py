import sys
from app.database import db

uids_to_delete = [
    "SAB_B_01-0000_2023",
    "SAB_B_01-04770_2023",
    "SAB_B_01-0888_2023",
    "SAB_B_01-09967_2023",
    "uid_79e8d4f2cbf24257b0bfed9d3947b6f8"
]

profiles_ref = db.reference('profiles')

print("Deleting duplicate/unwanted accounts...")
for uid in uids_to_delete:
    profile = profiles_ref.child(uid).get()
    if profile:
        profiles_ref.child(uid).delete()
        print(f"Deleted profile: {uid} ({profile.get('name')})")
    else:
        print(f"Profile {uid} already deleted or not found.")

print("\nDone.")
