import re

# Word-to-number mapping to catch sneaky users typing "zero seven one..."
NUMBER_WORDS = {
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
    'oh': '0' # Common slang for zero
}

# Red-flag dictionaries
SELF_HARM_KEYWORDS = ['suicide', 'kill myself', 'end it all', 'want to die', 'drink poison', 'hang myself']
VIOLENCE_KEYWORDS = ['kill you', 'beat you', 'stab', 'murder', 'gonna hurt you']
ANGRY_KEYWORDS = ['hate you', 'stupid', 'idiot', 'bitch', 'fuck you', 'useless']

def contains_phone_number(text):
    """Detects numbers even if the user tries to spell them out."""
    # 1. Check raw text first using standard Regex
    phone_pattern = r"(\+254|0|254)[17]\d{8}"
    
    # Remove all spaces and hyphens just in case they type "07 00 - 11..."
    compressed_text = re.sub(r'[\s\-]', '', text)
    if re.search(phone_pattern, compressed_text):
        return True

    # 2. Advanced NLP Mock: Convert words to numbers and check again
    text_lower = text.lower()
    for word, num in NUMBER_WORDS.items():
        text_lower = text_lower.replace(word, num)
    
    compressed_converted = re.sub(r'[\s\-]', '', text_lower)
    if re.search(phone_pattern, compressed_converted):
        return True

    return False

def analyze_safety(text):
    """
    Scans the message for dangerous intent. 
    In production, you would replace this block with an API call to an NLP Sentiment Model.
    """
    text_lower = text.lower()
    
    # 1. Check for Self-Harm (CRITICAL)
    if any(kw in text_lower for kw in SELF_HARM_KEYWORDS):
        return {
            'is_safe': False,
            'flag': 'self_harm',
            'system_reply': "⚠️ SYSTEM ALERT: We care about you. If you are feeling overwhelmed or hopeless, please reach out for help. Contact the Kenya Red Cross toll-free at 1199, or Niskize at 0900 620 800. You are not alone."
        }
        
    # 2. Check for Violence (CRITICAL)
    if any(kw in text_lower for kw in VIOLENCE_KEYWORDS):
        return {
            'is_safe': False,
            'flag': 'violence',
            'system_reply': "⚠️ SYSTEM ALERT: Threats of violence are strictly prohibited and illegal. This message has been blocked and reported to the system administrators."
        }

    # 3. Check for General Anger/Toxicity (Coaching)
    if any(kw in text_lower for kw in ANGRY_KEYWORDS):
        return {
            'is_safe': False,
            'flag': 'toxic',
            'system_reply': "🤖 AI Wingman: Take a deep breath. Words spoken in anger leave permanent scars. 'A gentle answer turns away wrath, but a harsh word stirs up anger.' Let's try to communicate with love and respect."
        }

    return {'is_safe': True}