import os
import logging
from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. Configuration & Secrets
HF_TOKEN = os.getenv("HF_TOKEN")
# Extract model ID to a variable so you can easily swap it later without digging through code
MODEL_ID = os.getenv("ICEBREAKER_MODEL_ID", "HuggingFaceH4/zephyr-7b-beta")

if not HF_TOKEN:
    logger.warning("HF_TOKEN environment variable not set. API calls will fail.")

# Initialize client
client = InferenceClient(model=MODEL_ID, token=HF_TOKEN)

def generate_custom_icebreakers(user_a_bio: str, user_b_bio: str) -> str:
    """
    Takes two bios, compares them, and returns 3 custom icebreakers using the HF Inference API.
    """
    # Safety check: If bios are empty, return fallbacks immediately to save API calls
    if not user_a_bio or not user_b_bio:
        return _get_fallback_icebreakers()

    system_message = (
        "You are a witty, charismatic dating assistant for university students at MMUST in Kakamega, Kenya. "
        "Read two student bios and write 3 short, clever icebreaker messages that User A can send to User B. "
        "Focus on shared interests or playfully teasing their differences. "
        "Format exactly as a numbered list (1., 2., 3.). Keep them under 2 sentences each. No hashtags. No emojis."
    )
    
    user_message = f"User A's bio: '{user_a_bio}'\nUser B's bio: '{user_b_bio}'\nGenerate the 3 icebreakers:"

    # THE FIX: Use the Chat Completion API. 
    # Hugging Face handles formatting the <|system|> tags for you automatically based on the model!
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]

    try:
        response = client.chat_completion(
            messages=messages,
            max_tokens=150,     # Note: chat_completion uses max_tokens instead of max_new_tokens
            temperature=0.7,
            top_p=0.9,
        )
        
        # Extract the generated text from the response object
        reply = response.choices[0].message.content.strip()
        return reply
        
    except HfHubHTTPError as e:
        logger.error(f"Hugging Face API Error (Check Token, Rate Limit, or Model Status): {e}")
    except Exception as e:
        logger.error(f"Unexpected AI Generation Error: {e}")
        
    # If the try block fails for any reason, return the safe fallback
    return _get_fallback_icebreakers()

def _get_fallback_icebreakers() -> str:
    """Returns safe, generic MMUST icebreakers if the AI is down."""
    return (
        "1. Hey, just matched! What's your favorite spot on campus?\n"
        "2. Looks like we both go to MMUST! How are your classes going?\n"
        "3. Hi! Ready to survive the semester together?"
    )

# For testing the script directly
if __name__ == "__main__":
    print("Testing Icebreaker Generation...\n")
    print(generate_custom_icebreakers("I love Java and coffee.", "Nursing student who loves Afrobeats."))