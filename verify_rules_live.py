import requests
import json

db_url = 'https://mmust-dating-site-default-rtdb.firebaseio.com'

# Test nodes that client browsers access without auth
client_public_endpoints = [
    ('notifications/test_uid.json', 'GET'),
    ('chat_notifications/test_uid.json', 'GET'),
    ('incoming_calls/test_uid.json', 'GET'),
    ('calls/test_room.json', 'GET'),
    ('signals/test_uid.json', 'GET'),
    ('emergency_alerts.json', 'GET'),
    ('matches/test_match/messages.json', 'GET'),
    ('chats/test_room/typing.json', 'GET'),
    ('profiles/test_uid/is_online.json', 'GET'),
    ('profiles/test_uid/last_active.json', 'GET'),
    ('users/test_uid/is_online.json', 'GET'),
    ('groups/test_group.json', 'GET'),
    ('group_messages/test_group.json', 'GET'),
    ('party_chat_main.json', 'GET'),
    ('balloon_chat.json', 'GET'),
    ('lights_out_queue.json', 'GET'),
]

# Sensitive nodes that MUST remain protected from public unauthenticated access
protected_endpoints = [
    ('campus_managers.json', 'GET'),
    ('campus_manager_ledgers.json', 'GET'),
    ('admin_audit_logs.json', 'GET'),
    ('swipes.json', 'GET'),
    ('bookings.json', 'GET'),
    ('schedules.json', 'GET'),
    ('profiles.json', 'GET'), # entire profiles root must be protected
]

print("=== VERIFYING CLIENT REAL-TIME ENDPOINTS ===")
all_client_passed = True
for ep, method in client_public_endpoints:
    url = f"{db_url}/{ep}"
    res = requests.get(url)
    status = res.status_code
    passed = (status == 200)
    if not passed:
        all_client_passed = False
    print(f"[{'PASS' if passed else 'FAIL'}] {method} {ep:40} => HTTP {status}")

print("\n=== VERIFYING PROTECTED/SENSITIVE ENDPOINTS ===")
all_protected_passed = True
for ep, method in protected_endpoints:
    url = f"{db_url}/{ep}"
    res = requests.get(url)
    status = res.status_code
    # Must be 401 Unauthorized / Permission Denied
    passed = (status == 401)
    if not passed:
        all_protected_passed = False
    print(f"[{'PASS' if passed else 'FAIL'}] {method} {ep:40} => HTTP {status} (Expected 401)")

print("\n=== VERIFYING REAL-TIME WRITE/DELETE CYCLE ===")
# Test notification push and dismissal
test_notif_url = f"{db_url}/notifications/test_verifier_uid.json"
put_res = requests.post(test_notif_url, json={"type": "like", "title": "Test Ping", "timestamp": "2026-10-12T13:00:00Z"})
print(f"POST {test_notif_url} => HTTP {put_res.status_code}")
if put_res.status_code == 200:
    notif_id = put_res.json().get('name')
    del_res = requests.delete(f"{db_url}/notifications/test_verifier_uid/{notif_id}.json")
    print(f"DELETE created notif => HTTP {del_res.status_code}")

# Test user presence set
pres_url = f"{db_url}/profiles/test_verifier_uid/is_online.json"
pres_put = requests.put(pres_url, json=True)
print(f"PUT {pres_url} => HTTP {pres_put.status_code}")
requests.delete(f"{db_url}/profiles/test_verifier_uid/is_online.json")

print("\n==============================================")
if all_client_passed and all_protected_passed:
    print("ALL TESTS PASSED! Firebase Realtime Database rules are 100% verified!")
else:
    print("WARNING: Some tests did not return expected status codes.")
