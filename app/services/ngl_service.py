import re
import random
import logging
from datetime import datetime, timedelta, timezone
from app.database import db

logger = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))

GAME_TEMPLATES = {
    "confessions": {
        "id": "confessions",
        "title": "Confessions",
        "emoji": "🤫",
        "prompt": "Send me anonymous confessions! I won't know who you are 🤫",
        "card_theme": "linear-gradient(135deg, #FF0844 0%, #FFB199 100%)",
        "placeholder": "Send me a confession I'll never guess..."
    },
    "crush": {
        "id": "crush",
        "title": "Secret Crush",
        "emoji": "💋",
        "prompt": "Confess your secret crush on me 💋 I won't know who sent it!",
        "card_theme": "linear-gradient(135deg, #F857A6 0%, #FF5858 100%)",
        "placeholder": "Drop your confession or hint here..."
    },
    "ama": {
        "id": "ama",
        "title": "Ask Me Anything",
        "emoji": "💬",
        "prompt": "Ask me anything honestly — 100% anonymous 💬",
        "card_theme": "linear-gradient(135deg, #667EEA 0%, #764BA2 100%)",
        "placeholder": "Ask whatever you've been wondering..."
    },
    "vibe": {
        "id": "vibe",
        "title": "Vibe Check",
        "emoji": "🔥",
        "prompt": "Describe my vibe in 3 words 🔥",
        "card_theme": "linear-gradient(135deg, #F093FB 0%, #F5576C 100%)",
        "placeholder": "Three words that describe me..."
    },
    "tea": {
        "id": "tea",
        "title": "Spill The Tea",
        "emoji": "😈",
        "prompt": "Spill some anonymous tea about me or campus 😈",
        "card_theme": "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
        "placeholder": "What's the tea? Don't hold back..."
    },
    "custom": {
        "id": "custom",
        "title": "Custom Prompt",
        "emoji": "✨",
        "prompt": "Send me an anonymous message ✨",
        "card_theme": "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",
        "placeholder": "Write your anonymous message..."
    }
}

SUGGESTED_PROMPTS = [
    "I've had a secret crush on you since first year...",
    "You have the most beautiful smile in campus ✨",
    "What would you do if I asked you out this Friday?",
    "You always look amazing in library LH2 📚",
    "Someone close to you has feelings for you...",
    "If I told you who I was, would you give me a chance?",
    "Your laugh is genuinely contagious 😊",
    "What is your biggest red flag that you're proud of?",
    "You are way out of my league but I still admire you.",
    "Be honest: who was your last campus crush?",
    "You give off main character energy 💅",
    "I saw you yesterday and couldn't stop looking...",
    "Tell me your most embarrassing campus memory!",
    "Who is your favorite person right now?",
    "I bet you don't even know I exist 🙈"
]


def sanitize_slug(raw_name: str) -> str:
    """Cleans a string into an alphanumeric URL-safe slug."""
    clean = re.sub(r'[^a-zA-Z0-9_-]', '', raw_name.lower().replace(' ', '_'))
    return clean[:24] if clean else "student"


def parse_device_hint(user_agent: str) -> str:
    """Parses standard HTTP User-Agent string into a friendly NGL-style device hint."""
    if not user_agent:
        return "Mobile Device"

    ua = user_agent.lower()
    os_name = "Device"
    browser = "Browser"

    if "iphone" in ua:
        os_name = "iPhone"
    elif "ipad" in ua:
        os_name = "iPad"
    elif "android" in ua:
        if "samsung" in ua:
            os_name = "Samsung Galaxy"
        else:
            os_name = "Android Phone"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "Apple Mac"
    elif "windows" in ua:
        os_name = "Windows PC"
    elif "linux" in ua:
        os_name = "Linux PC"

    if "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "chrome" in ua or "crios" in ua:
        browser = "Chrome"
    elif "firefox" in ua or "fxios" in ua:
        browser = "Firefox"
    elif "edge" in ua or "edg" in ua:
        browser = "Edge"
    elif "whatsapp" in ua:
        browser = "WhatsApp Web"

    return f"{os_name} • {browser}"


def get_or_create_user_link(user_id: str) -> dict:
    """
    Retrieves or generates the user's customized NGL anonymous link and settings.
    """
    if not user_id:
        return {"success": False, "error": "User ID required."}

    profile = db.reference(f'profiles/{user_id}').get() or {}
    slug = profile.get('ngl_slug')

    # If slug already exists, fetch link settings
    if slug:
        link_data = db.reference(f'ngl_links/{slug}').get()
        if link_data and isinstance(link_data, dict):
            game_type = link_data.get('game_type', 'confessions')
            template = GAME_TEMPLATES.get(game_type, GAME_TEMPLATES['confessions'])
            return {
                "success": True,
                "slug": slug,
                "prompt_text": link_data.get('prompt_text', template['prompt']),
                "game_type": game_type,
                "templates": GAME_TEMPLATES,
                "suggested_prompts": SUGGESTED_PROMPTS
            }

    # Generate new unique slug based on user's name or referral code
    raw_name = profile.get('name', 'student').split()[0]
    base_slug = sanitize_slug(raw_name)
    slug_candidate = f"{base_slug}_{random.randint(100, 999)}"

    # Ensure slug uniqueness
    counter = 1
    while db.reference(f'ngl_links/{slug_candidate}').get():
        slug_candidate = f"{base_slug}_{random.randint(1000, 9999)}"
        counter += 1
        if counter > 5:
            slug_candidate = f"ngl_{int(datetime.now().timestamp())[-6:]}"
            break

    initial_game = "confessions"
    initial_prompt = GAME_TEMPLATES[initial_game]["prompt"]

    link_record = {
        "user_id": user_id,
        "game_type": initial_game,
        "prompt_text": initial_prompt,
        "created_at": datetime.now(EAT).isoformat(),
        "active": True
    }

    db.reference(f'ngl_links/{slug_candidate}').set(link_record)
    db.reference(f'profiles/{user_id}').update({'ngl_slug': slug_candidate})

    logger.info(f"✨ Created NGL link for {user_id} -> {slug_candidate}")

    return {
        "success": True,
        "slug": slug_candidate,
        "prompt_text": initial_prompt,
        "game_type": initial_game,
        "templates": GAME_TEMPLATES,
        "suggested_prompts": SUGGESTED_PROMPTS
    }


def update_user_link(user_id: str, new_slug: str = None, game_type: str = None, custom_prompt: str = None) -> dict:
    """
    Updates the prompt text, game template, or custom slug for the user's NGL link.
    """
    if not user_id:
        return {"success": False, "error": "User ID required."}

    current = get_or_create_user_link(user_id)
    current_slug = current.get('slug')

    target_slug = current_slug
    if new_slug:
        clean_new = sanitize_slug(new_slug)
        if len(clean_new) < 3:
            return {"success": False, "error": "Handle must be at least 3 alphanumeric characters."}

        if clean_new != current_slug:
            existing = db.reference(f'ngl_links/{clean_new}').get()
            if existing and existing.get('user_id') != user_id:
                return {"success": False, "error": f"The link '{clean_new}' is already taken! Try another."}
            # Remove old link mapping and migrate
            db.reference(f'ngl_links/{current_slug}').delete()
            target_slug = clean_new
            db.reference(f'profiles/{user_id}').update({'ngl_slug': target_slug})

    # Validate template
    selected_game = game_type or current.get('game_type', 'confessions')
    template = GAME_TEMPLATES.get(selected_game, GAME_TEMPLATES['confessions'])

    final_prompt = custom_prompt.strip() if custom_prompt else template['prompt']

    payload = {
        "user_id": user_id,
        "game_type": selected_game,
        "prompt_text": final_prompt,
        "active": True,
        "updated_at": datetime.now(EAT).isoformat()
    }
    db.reference(f'ngl_links/{target_slug}').set(payload)

    return {
        "success": True,
        "slug": target_slug,
        "game_type": selected_game,
        "prompt_text": final_prompt,
        "message": "NGL link updated successfully!"
    }


def get_public_ngl_profile(slug: str) -> dict:
    """
    Fetches the public profile information needed to render the zero-login response page.
    """
    if not slug:
        return {"found": False, "error": "Link not found."}

    link_data = db.reference(f'ngl_links/{slug}').get()
    if not link_data or not isinstance(link_data, dict):
        return {"found": False, "error": "This anonymous confession link does not exist."}

    user_id = link_data.get('user_id')
    profile = db.reference(f'profiles/{user_id}').get() or {}

    first_name = profile.get('name', 'Comrade').split()[0]
    institution = profile.get('institution_name', 'MMUST')
    game_type = link_data.get('game_type', 'confessions')
    template = GAME_TEMPLATES.get(game_type, GAME_TEMPLATES['confessions'])

    return {
        "found": True,
        "slug": slug,
        "user_id": user_id,
        "recipient_first_name": first_name,
        "recipient_img": profile.get('img', '/static/img/placeholder.png'),
        "institution": institution,
        "prompt_text": link_data.get('prompt_text', template['prompt']),
        "game_type": game_type,
        "card_theme": template.get('card_theme'),
        "placeholder": template.get('placeholder'),
        "suggested_prompts": SUGGESTED_PROMPTS
    }


def submit_anonymous_confession(slug: str, message_text: str, user_agent: str = "", ip_address: str = "") -> dict:
    """
    Safely submits an anonymous confession from the web without requiring login.
    Runs text safety, logs anonymous hints (device / approximate campus time), and stores in inbox.
    """
    if not slug:
        return {"success": False, "error": "Invalid confession link."}

    text = (message_text or "").strip()
    if len(text) < 2:
        return {"success": False, "error": "Please type a message before sending."}
    if len(text) > 600:
        return {"success": False, "error": "Confession is too long (maximum 600 characters)."}

    # 1. Moderation Check (using existing moderation helper if available)
    try:
        from app.services.moderation import analyze_safety
        safety = analyze_safety(text)
        if not safety.get('is_safe', True):
            return {
                "success": False,
                "error": "This message could not be sent because it violates community safety guidelines."
            }
    except Exception as mod_err:
        logger.warning(f"Moderation check skipped or failed: {mod_err}")

    # 2. Resolve link and recipient
    link_data = db.reference(f'ngl_links/{slug}').get()
    if not link_data or not isinstance(link_data, dict):
        return {"success": False, "error": "This anonymous link is inactive or does not exist."}

    user_id = link_data.get('user_id')
    now_eat = datetime.now(EAT)

    # 3. Parse Device & Location Hints (for NGL Pro hints)
    device_hint = parse_device_hint(user_agent)
    recipient_profile = db.reference(f'profiles/{user_id}').get() or {}
    campus_name = recipient_profile.get('institution_name', 'MMUST Campus')
    location_hint = f"{campus_name} Area"

    msg_payload = {
        "text": text,
        "prompt": link_data.get('prompt_text', 'Anonymous Message'),
        "game_type": link_data.get('game_type', 'confessions'),
        "timestamp": now_eat.isoformat(),
        "time_formatted": now_eat.strftime("%I:%M %p"),
        "date_formatted": now_eat.strftime("%b %d"),
        "is_read": False,
        "device_hint": device_hint,
        "location_hint": location_hint,
        "slug": slug
    }

    inbox_ref = db.reference(f'ngl_inbox/{user_id}').push(msg_payload)

    # 4. Push in-app alert to recipient
    try:
        db.reference(f'notifications/{user_id}').push({
            "title": "🤫 New Anonymous Confession!",
            "message": f"Someone just sent you a secret confession on your NGL link! Open your inbox to read it.",
            "type": "ngl_confession",
            "timestamp": now_eat.isoformat(),
            "status": "unread"
        })
    except Exception as notif_err:
        logger.error(f"Error notifying recipient of confession: {notif_err}")

    logger.info(f"💌 Anonymous confession sent to {user_id} via /{slug} ({device_hint})")

    return {
        "success": True,
        "message_id": inbox_ref.key,
        "message": "Your confession has been delivered anonymously! 🔒"
    }


def get_user_inbox(user_id: str) -> list:
    """Retrieves all anonymous confessions for a user, sorted newest first."""
    if not user_id:
        return []

    raw = db.reference(f'ngl_inbox/{user_id}').get() or {}
    if not isinstance(raw, dict):
        return []

    messages = []
    for mid, mdata in raw.items():
        if isinstance(mdata, dict):
            messages.append({
                **mdata,
                "id": mid
            })

    messages.sort(key=lambda m: m.get('timestamp', ''), reverse=True)
    return messages


def delete_inbox_message(user_id: str, message_id: str) -> bool:
    """Permanently deletes a confession from the user's inbox."""
    try:
        db.reference(f'ngl_inbox/{user_id}/{message_id}').delete()
        return True
    except Exception as e:
        logger.error(f"Error deleting confession {message_id}: {e}")
        return False


def mark_inbox_message_read(user_id: str, message_id: str) -> bool:
    """Marks a confession as opened/read."""
    try:
        db.reference(f'ngl_inbox/{user_id}/{message_id}').update({'is_read': True})
        return True
    except Exception:
        return False
