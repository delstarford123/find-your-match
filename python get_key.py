import base64

pem_data = """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEpALO8QaYYjlrVifPH8A2yuIvoQoo
v2A/6dwOteFtHdSq322q73iEubNZp9bHRE65x3ory0muy7eyTMXA/a4hSQ==
-----END PUBLIC KEY-----"""

# 1. Clean the PEM string
clean_b64 = pem_data.replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "").replace("\n", "")

# 2. Decode to raw bytes
raw_bytes = base64.b64decode(clean_b64)

# 3. Web Push requires the 65-byte uncompressed point (strips the 26-byte ASN.1 header)
public_key_bytes = raw_bytes[-65:]

# 4. Encode to URL-Safe Base64 without padding
vapid_app_key = base64.urlsafe_b64encode(public_key_bytes).decode('utf-8').replace("=", "")

print("\n✅ COPY THIS STRING INTO swipe.html:\n")
print(vapid_app_key)
print("\n")