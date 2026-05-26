import os
import random
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, session
from app.database import db

# Kenya Timezone
EAT = timezone(timedelta(hours=3))

matches_bp = Blueprint('matches', __name__)

# Dynamically import your Hugging Face NLP Module
try:
    import importlib
    nlp = importlib.import_module('ml_pipeline.1_nlp_icebreakers.generator')
    generate_custom_icebreakers = nlp.generate_custom_icebreakers
except Exception as e:
    # Fallback function if AI is offline
    def generate_custom_icebreakers(a, b): return ["Hey! I saw we both study at MMUST. How's your semester?"]

@matches_bp.route('/api/swipe', methods=['POST'])
def record_swipe():
    data = request.json
    current_user_id = session.get('user_id')
    target_user_id = data.get('target_id')
    action = data.get('action') 
    timestamp = datetime.now(EAT).isoformat()

    if not current_user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    if not target_user_id or not action:
        return jsonify({"status": "error", "message": "Missing swipe data"}), 400

    try:
        # 1. Record the swipe
        db.reference(f'swipes/{current_user_id}/{target_user_id}').set({
            'action': action,
            'timestamp': timestamp
        })
        
        is_match = False
        match_details = {}

        if action == 'like':
            # Fetch profiles early so we can compare them for cool commonalities!
            current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
            target_profile = db.reference(f'profiles/{target_user_id}').get() or {}

            # 2. CHECK ALL MATCH CONDITIONS
            # A: Did they already swipe right on us?
            target_swipe = db.reference(f'swipes/{target_user_id}/{current_user_id}').get()
            target_swiped_right = target_swipe and target_swipe.get('action') == 'like'
            
            # B: Do they have a pending Secret Crush on us?
            target_crush = db.reference(f'secret_crushes/{target_user_id}/{current_user_id}').get()
            target_crushed_on_me = target_crush and target_crush.get('status') == 'pending'

            # If either condition is true, IT IS A MATCH!
            if target_swiped_right or target_crushed_on_me:
                is_match = True
                match_id = "_".join(sorted([current_user_id, target_user_id]))
                
                # If they matched via crush, update the crush database to keep it clean
                if target_crushed_on_me:
                    db.reference(f'secret_crushes/{target_user_id}/{current_user_id}').update({'status': 'matched'})
                    db.reference(f'secret_crushes/{current_user_id}/{target_user_id}').set({'timestamp': timestamp, 'status': 'matched'})
                
                # 3. FIGURE OUT *WHY* THEY MATCHED (To make the UI awesome)
                match_reason = "You both liked each other! ✨"
                
                if target_crushed_on_me:
                    match_reason = "OMG! They had a Secret Crush on you! 🤫❤️"
                elif current_profile.get('intent') and current_profile.get('intent') != 'none' and current_profile.get('intent') == target_profile.get('intent'):
                    # They have the exact same relationship intent!
                    intent_map = {'coffee': '☕ Coffee', 'study': '📚 Study Sessions', 'event': '🎉 Events', 'relationship': '💘 A Relationship'}
                    shared_intent = intent_map.get(current_profile.get('intent'), '')
                    if shared_intent:
                        match_reason = f"You are both looking for {shared_intent}!"
                else:
                    # Let's check for shared words in their bios!
                    my_bio_words = set(current_profile.get('bio', '').lower().replace('.', '').replace(',', '').split())
                    their_bio_words = set(target_profile.get('bio', '').lower().replace('.', '').replace(',', '').split())
                    # Filter out boring words
                    stop_words = {'i', 'am', 'a', 'the', 'and', 'to', 'for', 'in', 'of', 'my', 'is', 'at', 'on', 'with', 'student', 'mmust', 'like', 'love', 'looking', 'here'}
                    common_words = (my_bio_words & their_bio_words) - stop_words
                    
                    if common_words:
                        best_word = list(common_words)[0].capitalize()
                        match_reason = f"You both mentioned '{best_word}' in your bios! 🎯"

                # 4. Save Match Entry to Database
                db.reference(f'matches/{match_id}').set({
                    'users': {current_user_id: True, target_user_id: True},
                    'matched_at': timestamp,
                    'last_message': 'You matched! Say hi.',
                    'last_message_time': timestamp,
                    'match_reason': match_reason # Save it so we can show it in chats later!
                })

                # 5. Build match details for the frontend celebration!
                match_details = {
                    'id': match_id,
                    'name': target_profile.get('name', 'Student').split(' ')[0],
                    'img': target_profile.get('img', '/static/img/placeholder.png'),
                    'reason': match_reason
                }

                # 6. TRIGGER PUSH NOTIFICATION & AI INTRO
                try:
                    from flask import current_app
                    socketio = current_app.extensions.get('socketio')
                    if socketio:
                        # Normal match buzz
                        current_name = current_profile.get('name', 'Someone').split(' ')[0]
                        # We need to import these or move them to a shared service
                        # For now, we'll try to call them if they are in the app context or just emit directly
                        socketio.emit('receive_notification', {
                            'title': 'New Match! ❤️',
                            'message': f'{current_name} liked you back!',
                            'type': 'success'
                        }, room=target_user_id)
                except Exception as e:
                    print(f"Notification failed: {e}")

                return jsonify({
                "status": "success", 
                "match": is_match,
                "match_details": match_details if is_match else None
                })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@matches_bp.route('/api/icebreakers', methods=['POST'])
def get_icebreakers():
    data = request.json
    
    user_a_bio = data.get('my_bio', "I'm a student at MMUST.")
    user_b_bio = data.get('match_bio', "I study here too.")
    
    # Trigger the AI (Hugging Face / Local Model)
    icebreakers_text = generate_custom_icebreakers(user_a_bio, user_b_bio)
    
    return jsonify({
        "status": "success", 
        "icebreakers": icebreakers_text
    })