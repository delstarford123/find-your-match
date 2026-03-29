import os
import datetime
from flask import Blueprint, request, jsonify, session
from app.database import db  # Use your existing Firebase connection

matches_bp = Blueprint('matches', __name__)

# Dynamically import your Hugging Face NLP Module
try:
    import importlib
    nlp = importlib.import_module('ml_pipeline.1_nlp_icebreakers.generator')
    generate_custom_icebreakers = nlp.generate_custom_icebreakers
except Exception as e:
    print(f"⚠️ NLP Module not loaded: {e}")
    # Fallback function if AI is offline
    def generate_custom_icebreakers(a, b): return ["Hey! I saw we both study at MMUST. How's your semester?"]

@matches_bp.route('/api/swipe', methods=['POST'])
def record_swipe():
    data = request.json
    
    current_user_id = session.get('user_id') # Get from session for security
    target_user_id = data.get('target_id')
    action = data.get('action') # 'like' or 'dislike'
    timestamp = datetime.datetime.now().isoformat()
    
    if not current_user_id or not target_user_id:
        return jsonify({"status": "error", "message": "Missing IDs"}), 400

    # 1. SAVE TO FIREBASE (Cloud Sync)
    try:
        db.reference('swipes').push({
            'user_id': current_user_id,
            'target_id': target_id,
            'action': action,
            'timestamp': timestamp
        })
        
        # 2. CHECK FOR A MATCH (Optional but recommended)
        # If Target has already 'liked' Current User, it's a MATCH!
        is_match = False
        reciprocal_swipe = db.reference('swipes').order_by_child('user_id').equal_to(target_user_id).get()
        if reciprocal_swipe:
            for s_id, s_data in reciprocal_swipe.items():
                if s_data.get('target_id') == current_user_id and s_data.get('action') == 'like':
                    is_match = True
                    # Create a match record
                    db.reference('matches').push({
                        'users': sorted([current_user_id, target_user_id]),
                        'created_at': timestamp
                    })

        return jsonify({
            "status": "success", 
            "match": is_match,
            "message": "Swipe recorded in Firebase"
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