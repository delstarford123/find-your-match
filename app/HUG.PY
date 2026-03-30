import os
import requests

# ==========================================
# AI INTEGRATION: PRIVATE HF ENDPOINT
# ==========================================
HF_TOKEN = os.getenv("HF_TOKEN")

# PASTE YOUR NEW ENDPOINT URL HERE
API_URL = "YOUR_NEW_ENDPOINT_URL_HERE"

def get_ai_companion_response(user_text):
    """Connects directly to your private, paid Hugging Face Endpoint."""
    if not HF_TOKEN:
        print("⚠️ HF_TOKEN is missing!")
        return "My AI brain is currently resting. (API Key missing!)"

    headers = {
        "Authorization": f"Bearer {HF_TOKEN}",
        "Content-Type": "application/json"
    }

    # Your exact TinyLlama prompt format
    prompt = f"<|system|>\nYou are a friendly, flirty, and supportive AI dating companion for university students at MMUST. Keep it clean and encouraging.</s>\n<|user|>\n{user_text}</s>\n<|assistant|>\n"
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": 150,
            "temperature": 0.7,
            "return_full_text": False
        }
    }

    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        
        # If the server was sleeping (Scale to Zero)
        if response.status_code == 503:
            return "My AI brain is waking up! Give me 20 seconds and ask me again."
            
        response.raise_for_status()
        data = response.json()
        
        if isinstance(data, list) and len(data) > 0:
            reply = data[0].get('generated_text', '').strip()
            return reply if reply else "I'm listening, tell me more!"
            
        return "That's interesting! What else is on your mind?"

    except Exception as e:
        print(f"⚠️ Private Endpoint Error: {e}")
        return "I'm having a bit of a lag! Try again?"