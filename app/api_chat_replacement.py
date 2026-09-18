# ==========================================
# FIREBASE REST API ENDPOINTS (REPLACED WEBSOCKETS)
# ==========================================
import threading
from flask import request

@app.route('/api/chat/enter', methods=['POST'])
def api_enter_chat():
    user_id = session.get('user_id')
    partner_id = request.json.get('partner_id') if request.json else None
    
    if user_id and partner_id:
        match_id = f"match_{min(user_id, partner_id)}_{max(user_id, partner_id)}"
        messages_ref = db.reference(f'matches/{match_id}/messages')
        history = messages_ref.get() or {}
        updates = {}
        if isinstance(history, dict):
            for msg_key, msg in history.items():
                if isinstance(msg, dict) and msg.get('sender_id') == partner_id and msg.get('status') != 'read':
                    updates[f'{msg_key}/status'] = 'read'
        elif isinstance(history, list):
            for index, msg in enumerate(history):
                if isinstance(msg, dict) and msg.get('sender_id') == partner_id and msg.get('status') != 'read':
                    updates[f'{index}/status'] = 'read'
        if updates:
            messages_ref.update(updates)
            
    return jsonify({"success": True})

@app.route('/api/chat/typing', methods=['POST'])
def api_typing():
    user_id = session.get('user_id')
    receiver_id = request.json.get('receiver_id') if request.json else None
    is_typing = request.json.get('is_typing', False) if request.json else False
    
    if user_id and receiver_id:
        room_id = f"{min(user_id, receiver_id)}_{max(user_id, receiver_id)}"
        db.reference(f'chats/{room_id}/typing/{user_id}').set(is_typing)
    
    return jsonify({"success": True})

@app.route('/api/chat/send', methods=['POST'])
def api_send_message():
    sender_id = session.get('user_id')
    if not sender_id: return jsonify({"success": False, "message": "Unauthorized"}), 401
    
    data = request.json or {}
    receiver_id = data.get('receiver_id')
    msg_text = data.get('text', '').strip()
    msg_type = data.get('type', 'text')
    temp_id = data.get('temp_id')
    file_data = data.get('file_data')
    
    if not receiver_id or (not msg_text and not file_data):
        return jsonify({"success": False}), 400
        
    now_eat = datetime.now(EAT).isoformat()
    
    # 1. Shadowban Check
    try:
        sender_profile = db.reference(f'profiles/{sender_id}').get() or {}
        if sender_profile.get('is_shadowbanned'):
            return jsonify({"success": True, "shadowbanned": True, "temp_id": temp_id})
    except: pass
    
    # 2. AI Companion
    if receiver_id == 'AI_COMPANION':
        if msg_type != 'text': return jsonify({"success": False})
        
        db.reference(f'matches/match_{sender_id}_AI_COMPANION/messages').push({
            'sender_id': sender_id, 'text': msg_text, 'timestamp': now_eat, 'type': 'text', 'status': 'read'
        })
        db.reference(f'chats/match_{sender_id}_AI_COMPANION/typing/AI_COMPANION').set(True)
        
        current_user_gender = sender_profile.get('gender', 'unknown')
        def ai_worker():
            try:
                ai_reply = get_ai_companion_response(msg_text, user_gender=current_user_gender)
                db.reference(f'chats/match_{sender_id}_AI_COMPANION/typing/AI_COMPANION').set(False)
                db.reference(f'matches/match_{sender_id}_AI_COMPANION/messages').push({
                    'sender_id': 'AI_COMPANION', 'text': ai_reply, 'timestamp': datetime.now(EAT).isoformat(), 'type': 'text', 'status': 'read'
                })
            except Exception as e: logger.error(f"AI Worker Error: {e}")
            
        threading.Thread(target=ai_worker).start()
        return jsonify({"success": True, "temp_id": temp_id})
        
    # 3. Moderation
    if msg_type == 'text':
        safety_check = analyze_safety(msg_text)
        if not safety_check.get('is_safe', True):
            if safety_check.get('flag') in ['self_harm', 'violence']:
                db.reference('admin_alerts').push({
                    'sender': sender_id, 'receiver': receiver_id, 'message': msg_text, 'flag': safety_check['flag'], 'timestamp': now_eat
                })
            return jsonify({"success": False, "system_reply": safety_check.get('system_reply')}), 400
            
        if contains_phone_number(msg_text):
            return jsonify({"success": False, "system_reply": "SYSTEM ALERT: Sharing phone numbers is restricted."}), 400
            
    match_id = f"match_{min(sender_id, receiver_id)}_{max(sender_id, receiver_id)}"
    file_url = None
    
    if msg_type in ['image', 'video', 'audio'] and file_data:
        media_ref = db.reference('chat_media').push({
            'sender_id': sender_id, 'match_id': match_id, 'type': msg_type, 'data': file_data, 'timestamp': now_eat
        })
        file_url = file_data
        
    message_payload = {
        'sender_id': sender_id,
        'text': msg_text if msg_type == 'text' else f"Sent a {msg_type}",
        'timestamp': now_eat,
        'type': msg_type,
        'status': 'sent'
    }
    if file_url: message_payload['file_url'] = file_url
    
    try:
        new_msg_ref = db.reference(f'matches/{match_id}/messages').push(message_payload)
        db.reference(f'matches/{match_id}').update({
            'last_message': message_payload['text'],
            'last_message_time': now_eat,
            f'users/{sender_id}': True,
            f'users/{receiver_id}': True
        })
        
        return jsonify({
            "success": True, 
            "temp_id": temp_id, 
            "msg_id": new_msg_ref.key, 
            "status": "sent",
            "message_payload": message_payload
        })
    except Exception as e:
        logger.error(f"Save message error: {e}")
        return jsonify({"success": False}), 500
