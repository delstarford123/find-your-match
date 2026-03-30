import os
import logging
from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. Configuration & Secrets
HF_TOKEN = os.getenv("HF_TOKEN")
# swapping to mistral-7b-instruct-v0.2 as it's generally faster for short chat tasks
MODEL_ID = os.getenv("ICEBREAKER_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.2")

if not HF_TOKEN:
    logger.error("HF_TOKEN is missing. AI matching features will be disabled.")

# Initialize client with a timeout to keep the web app responsive
client = InferenceClient(model=MODEL_ID, token=HF_TOKEN, timeout=10)

def generate_custom_icebreakers(user_a_bio: str, user_b_bio: str) -> str:
    """
    Analyzes two MMUST student bios to generate 3 witty, localized icebreakers.
    """
    if not user_a_bio or not user_b_bio:
        return _get_fallback_icebreakers()

    # The secret sauce: Adding Kakamega context directly into the system prompt
    system_message = (
        "You are 'MatchAI', a witty dating coach for students at MMUST (Masinde Muliro University) in Kakamega. "
        "Use Kenyan campus slang sparingly (like 'vibe', 'form', 'sherehe'). "
        "Create 3 distinct icebreakers for User A to send to User B based on their bios. "
        "Rules: Number them 1-3. No emojis. Under 20 words each. "
        "If bios mention classes, tease them about the Kakamega rain or library sessions."
    )
    
    user_message = f"User A: {user_a_bio}\nUser B: {user_b_bio}\nGenerate 3 short lines:"

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

    try:
        # Using stream=False for simpler handling in a synchronous web request
        response = client.chat_completion(
            messages=messages,
            max_tokens=120, 
            temperature=0.8, # Increased for more 'wit'
            top_p=0.9,
        )
        
        reply = response.choices[0].message.content.strip()
        
        # Validation: Ensure the AI actually returned a list
        if "1." in reply:
            return reply
        else:
            logger.warning("AI output format invalid. Using fallbacks.")
            return _get_fallback_icebreakers()
            
    except HfHubHTTPError as e:
        logger.error(f"HF API Error: {e}")
    except Exception as e:
        logger.error(f"AI Generation Timeout or Error: {e}")
        
    return _get_fallback_icebreakers()

def _get_fallback_icebreakers() -> str:
    """Localized fallback icebreakers for MMUST students."""
    return (
        "1. I saw we both survived that Kakamega downpour today! Coffee at Savoury to dry off?\n"
        "2. Your bio mentioned classes—are you also hiding in the library all week?\n"
        "3. Hey! The AI says our vibes match. Want to grab lunch at MCU?"
    )

if __name__ == "__main__":
    # Test case: Comp Sci student vs Agriculture student
    print(generate_custom_icebreakers(
        "3rd year CS student. I spend too much time coding in Java.", 
        "Agriculture student. I love plants more than people."
    ))