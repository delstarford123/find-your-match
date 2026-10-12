import json
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests

with open('rules.json', 'r', encoding='utf-8') as f:
    rules = json.load(f)

creds = service_account.Credentials.from_service_account_file(
    'firebase_key.json',
    scopes=['https://www.googleapis.com/auth/firebase.database', 'https://www.googleapis.com/auth/userinfo.email']
)
creds.refresh(Request())
token = creds.token
db_url = 'https://mmust-dating-site-default-rtdb.firebaseio.com'

headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
res = requests.put(f'{db_url}/.settings/rules.json', json=rules, headers=headers)

print('Deploy Status Code:', res.status_code)
print('Response:', res.text[:200])

if res.status_code == 200:
    print('SUCCESS: Database rules deployed to live Firebase Realtime Database!')
else:
    print('FAILURE: Could not deploy rules.')
