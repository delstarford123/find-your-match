import os
import random
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, session
from app.database import db, get_all_profiles

logger = logging.getLogger(__name__)

# East Africa Time
EAT = timezone(timedelta(hours=3))

def requires_diamond_subscription_api(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user_id = session.get('user_id')
        if not current_user_id:
            return jsonify({"success": False, "status": "error", "message": "Unauthorized. Please log in."}), 401
            
        user_data = db.reference(f'profiles/{current_user_id}').get() or {}
        is_paid = user_data.get('is_paid', False)
        package = user_data.get('subscription_package', 'gold')
        expiry_str = user_data.get('subscription_expiry')
        
        has_expired = False
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) > expiry_dt:
                    has_expired = True
            except: pass
            
        if not is_paid or has_expired:
            if is_paid and has_expired:
                db.reference(f'profiles/{current_user_id}').update({'is_paid': False})
            return jsonify({"success": False, "status": "error", "message": "Your subscription has expired. Please renew."}), 402
            
        if package != 'diamond':
            return jsonify({
                "success": False, 
                "status": "error", 
                "message": "💎 Upgrade to the Diamond Package (100 KSH/month) to access this premium feature!"
            }), 403
            
        return f(*args, **kwargs)
    return decorated_function

v3_matching_bp = Blueprint('v3_matching', __name__, url_prefix='/api/v3')

@v3_matching_bp.route('/swipe', methods=['POST'])
def record_swipe():
    """
    V3 Swiping API with strict heterosexual validation and perfect match indicators.
    """
    data = request.json or {}
    current_user_id = session.get('user_id')
    target_user_id = data.get('target_id')
    action = data.get('action')
    timestamp = datetime.now(EAT).isoformat()

    if not current_user_id:
        return jsonify({"status": "error", "message": "Unauthorized. Please log in."}), 401
        
    if not target_user_id or not action:
        return jsonify({"status": "error", "message": "Missing target_id or action parameters."}), 400

    try:
        # 1. Fetch current profile and target profile for strict validation
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        target_profile = db.reference(f'profiles/{target_user_id}').get() or {}

        current_gender = str(current_profile.get('gender', '')).strip().lower()
        target_gender = str(target_profile.get('gender', '')).strip().lower()

        # 2. Strict Heterosexual Constraint
        if current_gender and target_gender:
            if current_gender == target_gender:
                return jsonify({
                    "status": "error", 
                    "message": "Strict campus rules: Under V3 API versioning, same-sex matches are disabled. Go to Settings to toggle V3 settings."
                }), 400

        # 3. Record the swipe in Firebase
        db.reference(f'swipes/{current_user_id}/{target_user_id}').set({
            'action': action,
            'timestamp': timestamp
        })

        is_match = False
        match_details = {}

        if action == 'like':
            # Check if they swiped right on us, or if they have a pending secret crush on us
            target_swipe = db.reference(f'swipes/{target_user_id}/{current_user_id}').get()
            target_swiped_right = target_swipe and target_swipe.get('action') == 'like'
            
            target_crush = db.reference(f'secret_crushes/{target_user_id}/{current_user_id}').get()
            target_crushed_on_me = target_crush and target_crush.get('status') == 'pending'

            if target_swiped_right or target_crushed_on_me:
                is_match = True
                match_id = "_".join(sorted([current_user_id, target_user_id]))

                # Clean up crush status
                if target_crushed_on_me:
                    db.reference(f'secret_crushes/{target_user_id}/{current_user_id}').update({'status': 'matched'})
                    db.reference(f'secret_crushes/{current_user_id}/{target_user_id}').set({'timestamp': timestamp, 'status': 'matched'})

                # Dynamic Compatibility calculations for "Perfect Match"
                base_score = target_profile.get('ai_score', random.randint(65, 80))
                my_intent = current_profile.get('intent', 'none')
                target_intent = target_profile.get('intent', 'none')
                
                bonus = 0
                if my_intent != 'none' and target_intent == my_intent:
                    bonus += 10
                    
                compatibility_score = min(base_score + bonus, 99)
                is_perfect_match = compatibility_score > 80

                match_reason = "You both liked each other! ✨"
                if target_crushed_on_me:
                    match_reason = "OMG! They had a Secret Crush on you! 🤫❤️"
                elif is_perfect_match:
                    match_reason = f"Perfect match! You share a high {compatibility_score}% compatibility index! 🎯"

                # Save match record
                db.reference(f'matches/{match_id}').set({
                    'users': {current_user_id: True, target_user_id: True},
                    'matched_at': timestamp,
                    'last_message': 'You matched! Say hi.',
                    'last_message_time': timestamp,
                    'match_reason': match_reason
                })

                match_details = {
                    'id': match_id,
                    'name': target_profile.get('name', 'Student').split(' ')[0],
                    'img': target_profile.get('img', '/static/img/placeholder.png'),
                    'reason': match_reason,
                    'is_perfect_match': is_perfect_match,
                    'compatibility': compatibility_score
                }

                # Try emitting websocket event
                try:
                    from flask import current_app
                    socketio = current_app.extensions.get('socketio')
                    if socketio:
                        current_name = current_profile.get('name', 'Someone').split(' ')[0]
                        socketio.emit('receive_notification', {
                            'title': 'New V3 Match! ❤️',
                            'message': f'{current_name} liked you back! Check your Perfect Matches.',
                            'type': 'success'
                        }, room=target_user_id)
                except Exception as e:
                    logger.error(f"Failed to emit V3 match socket event: {e}")

        return jsonify({
            "status": "success",
            "match": is_match,
            "match_details": match_details if is_match else None
        })

    except Exception as e:
        logger.error(f"Error in V3 Swipe: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@v3_matching_bp.route('/auto-match', methods=['POST'])
def auto_match():
    """
    Automated matchmaker that pairs a user with their most compatible paid opposite-sex user.
    """
    current_user_id = session.get('user_id')
    timestamp = datetime.now(EAT).isoformat()

    if not current_user_id:
        return jsonify({"success": False, "message": "Unauthorized"}), 401

    try:
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        current_gender = str(current_profile.get('gender', '')).strip().lower()
        
        if not current_gender:
            return jsonify({"success": False, "message": "Please configure your gender in settings before auto-matching."}), 400

        all_profiles = get_all_profiles()
        user_swipes = db.reference(f'swipes/{current_user_id}').get() or {}

        best_target = None
        best_score = 90 # Minimum auto-match threshold (>90%)

        for p in all_profiles:
            p_id = p.get('id')
            p_gender = str(p.get('gender', '')).strip().lower()
            
            # Opp-gender check
            if p_gender == current_gender or not p_gender:
                continue
            if p_id == current_user_id or p_id in user_swipes or not p.get('is_paid'):
                continue

            # Calculate compatibility
            comp = p.get('ai_score', random.randint(70, 85))
            if current_profile.get('intent') == p.get('intent') and current_profile.get('intent') != 'none':
                comp += 10
            
            score = min(comp, 99)
            if score > best_score:
                best_score = score
                best_target = p

        if not best_target:
            return jsonify({"success": False, "message": "No extremely high-compatibility matches (>90%) found today. Keep swiping!"}), 404

        target_id = best_target['id']
        match_id = "_".join(sorted([current_user_id, target_id]))

        # Register mutual swipes to simulate standard match
        db.reference(f'swipes/{current_user_id}/{target_id}').set({'action': 'like', 'timestamp': timestamp})
        db.reference(f'swipes/{target_id}/{current_user_id}').set({'action': 'like', 'timestamp': timestamp})

        # Save match
        db.reference(f'matches/{match_id}').set({
            'users': {current_user_id: True, target_id: True},
            'matched_at': timestamp,
            'last_message': 'Auto-matched! Start the conversation.',
            'last_message_time': timestamp,
            'match_reason': f"Smart Auto-Matchmaker: You share an extreme {best_score}% compatibility index! 🌌"
        })

        return jsonify({
            "success": True,
            "message": "Dynamic match found! Say hello to your new match.",
            "match": {
                "name": best_target.get('name', 'Student').split(' ')[0],
                "img": best_target.get('img', '/static/img/placeholder.png'),
                "compatibility": best_score,
                "partner_id": target_id
            }
        })

    except Exception as e:
        logger.error(f"Auto Match Error: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@v3_matching_bp.route('/radar', methods=['GET'])
@requires_diamond_subscription_api
def compatibility_radar():
    """
    Locates top opposite-gender premium profiles for the logged-in user sorted by score.
    """
    current_user_id = session.get('user_id')
    if not current_user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    try:
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        current_gender = str(current_profile.get('gender', '')).strip().lower()

        all_profiles = get_all_profiles()
        radar_list = []

        for p in all_profiles:
            p_id = p.get('id')
            p_gender = str(p.get('gender', '')).strip().lower()

            if p_id == current_user_id or not p.get('is_paid') or not p.get('is_visible', True):
                continue
            # opposite gender check
            if current_gender and p_gender and current_gender == p_gender:
                continue

            comp = p.get('ai_score', random.randint(65, 80))
            if current_profile.get('intent') == p.get('intent') and current_profile.get('intent') != 'none':
                comp += 10
            
            radar_list.append({
                'id': p_id,
                'name': p.get('name', 'Student').split(' ')[0],
                'img': p.get('img', '/static/img/placeholder.png'),
                'institution': p.get('institution_name', 'MMUST'),
                'course': p.get('course', 'Undergrad'),
                'compatibility': min(comp, 99)
            })

        # Sort by compatibility score descending
        radar_list.sort(key=lambda x: x['compatibility'], reverse=True)

        return jsonify({
            "status": "success",
            "radar": radar_list[:10] # Top 10
        })

    except Exception as e:
        logger.error(f"Compatibility Radar Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@v3_matching_bp.route('/spotify/share', methods=['POST'])
@requires_diamond_subscription_api
def share_spotify_playlist():
    """
    Emails a flirty mixtape playlist to a selected partner profile.
    """
    current_user_id = session.get('user_id')
    if not current_user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    target_id = data.get('target_id')
    playlist_url = data.get('playlist_url', '').strip()
    
    if not target_id or not playlist_url:
        return jsonify({'success': False, 'message': 'Target student and Playlist URL are required.'}), 400
        
    try:
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        target_profile = db.reference(f'profiles/{target_id}').get() or {}
        
        target_email = target_profile.get('email')
        target_name = target_profile.get('name', 'Comrade')
        sender_name = current_profile.get('name', 'Someone')
        
        if not target_email:
            return jsonify({'success': False, 'message': 'Target student email not found.'}), 404
            
        from app.email_service import send_spotify_playlist_email
        send_spotify_playlist_email(target_email, target_name, sender_name, playlist_url)
        
        return jsonify({'success': True, 'message': f' mixtape playlist shared successfully with {target_name.split(" ")[0]}!'})
    except Exception as e:
        logger.error(f"Spotify Playlist Share Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@v3_matching_bp.route('/meetup/radar', methods=['GET'])
@requires_diamond_subscription_api
def meetup_radar():
    """
    Returns opposite-gender nearby paid users with mock geographical distance cards.
    """
    current_user_id = session.get('user_id')
    if not current_user_id:
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
    try:
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        current_gender = str(current_profile.get('gender', '')).strip().lower()
        
        all_profiles = get_all_profiles()
        radar_list = []
        
        for p in all_profiles:
            p_id = p.get('id')
            p_gender = str(p.get('gender', '')).strip().lower()
            
            if p_id == current_user_id or not p.get('is_paid') or not p.get('is_visible', True):
                continue
                
            # Strict opposite gender check
            if current_gender and p_gender and current_gender == p_gender:
                continue
                
            # Mock geographical distance
            distance = round(random.uniform(0.2, 2.5), 1)
            
            radar_list.append({
                'id': p_id,
                'name': p.get('name', 'Student').split(' ')[0],
                'img': p.get('img', '/static/img/placeholder.png'),
                'course': p.get('course', p.get('major', 'Comrade')),
                'institution': p.get('institution_name', 'MMUST'),
                'distance': distance
            })
            
        radar_list.sort(key=lambda x: x['distance'])
        return jsonify({'status': 'success', 'radar': radar_list[:6]})
    except Exception as e:
        logger.error(f"Meetup Radar Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@v3_matching_bp.route('/meetup/request', methods=['POST'])
@requires_diamond_subscription_api
def meetup_request():
    """
    Sends a geographic meetup request via SocketIO and email to an opposite-sex student.
    """
    current_user_id = session.get('user_id')
    if not current_user_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
    data = request.json or {}
    target_id = data.get('target_id')
    
    if not target_id:
        return jsonify({'success': False, 'message': 'Target student is required.'}), 400
        
    try:
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        target_profile = db.reference(f'profiles/{target_id}').get() or {}
        
        current_gender = str(current_profile.get('gender', '')).strip().lower()
        target_gender = str(target_profile.get('gender', '')).strip().lower()
        
        # Strict opposite gender check
        if current_gender and target_gender and current_gender == target_gender:
            return jsonify({'success': False, 'message': 'Strict rules: Meetups are restricted to opposite-gender students only!'}), 400
            
        target_email = target_profile.get('email')
        target_name = target_profile.get('name', 'Comrade')
        sender_name = current_profile.get('name', 'Someone')
        
        if not target_email:
            return jsonify({'success': False, 'message': 'Target student email not found.'}), 404
            
        # Send Email Alert
        from app.email_service import send_meetup_request_email
        send_meetup_request_email(target_email, target_name, sender_name)
        
        # Trigger SocketIO Real-Time Buzz
        try:
            from flask import current_app
            socketio = current_app.extensions.get('socketio')
            if socketio:
                socketio.emit('receive_notification', {
                    'title': '📍 Meetup Request!',
                    'message': f'{sender_name} is nearby and wants to meet up with you! Check your email.',
                    'type': 'info'
                }, room=target_id)
        except Exception as se:
            logger.error(f"Failed to emit meetup socket alert: {se}")
            
        return jsonify({'success': True, 'message': f'Geographical meetup request sent to {target_name.split(" ")[0]} successfully!'})
    except Exception as e:
        logger.error(f"Meetup Request Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


import math

def calculate_distance(lat1, lon1, lat2, lon2):
    # Radius of the Earth in km
    R = 6371.0
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    distance = R * c
    return distance # in kilometers


@v3_matching_bp.route('/location/update', methods=['POST'])
@requires_diamond_subscription_api
def update_user_location():
    """
    Updates the logged-in user's GPS coordinates and scans for nearby opposite-sex paid Diamond/premium users.
    If nearby users are detected, it creates a proximity proposal and notifies them.
    """
    current_user_id = session.get('user_id')
    data = request.json or {}
    
    try:
        latitude = float(data.get('latitude'))
        longitude = float(data.get('longitude'))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid coordinates provided.'}), 400
        
    try:
        now_eat = datetime.now(EAT).isoformat()
        
        # 1. Update user location in DB
        location_data = {
            'latitude': latitude,
            'longitude': longitude,
            'timestamp': now_eat
        }
        db.reference(f'profiles/{current_user_id}/location').set(location_data)
        
        # Fetch current user profile to verify gender
        current_profile = db.reference(f'profiles/{current_user_id}').get() or {}
        current_gender = str(current_profile.get('gender', '')).strip().lower()
        
        if not current_gender:
            return jsonify({'success': False, 'message': 'Please set your gender in settings before using proximity matching.'}), 400
            
        # 2. Scan all paid profiles for opposite gender within 1 KM
        all_profiles = get_all_profiles()
        nearby_count = 0
        created_proposal = None
        
        for p in all_profiles:
            p_id = p.get('id')
            p_gender = str(p.get('gender', '')).strip().lower()
            
            if p_id == current_user_id or not p.get('is_paid') or not p.get('is_visible', True):
                continue
                
            # Must be opposite gender
            if current_gender == p_gender or not p_gender:
                continue
                
            # Grab partner location
            partner_loc = p.get('location') or {}
            partner_lat = partner_loc.get('latitude')
            partner_lng = partner_loc.get('longitude')
            partner_time = partner_loc.get('timestamp')
            
            if partner_lat is None or partner_lng is None:
                continue
                
            # Verify partner updated location in last 24 hours
            try:
                p_dt = datetime.fromisoformat(partner_time.replace('Z', '+00:00'))
                if datetime.now(timezone.utc) - p_dt > timedelta(hours=24):
                    continue
            except:
                pass
                
            # Calculate distance
            dist = calculate_distance(latitude, longitude, float(partner_lat), float(partner_lng))
            if dist <= 1.0:  # Within 1 KM radius
                nearby_count += 1
                
                # Create a deterministic proposal key
                proposal_id = f"proposal_{min(current_user_id, p_id)}_{max(current_user_id, p_id)}"
                proposal_ref = db.reference(f'proximity_proposals/{proposal_id}')
                
                existing = proposal_ref.get()
                if not existing:
                    proposal_data = {
                        'id': proposal_id,
                        'user_a_id': current_user_id,
                        'user_b_id': p_id,
                        'user_a_status': 'pending',
                        'user_b_status': 'pending',
                        'user_a_name': current_profile.get('name', 'Comrade').split(' ')[0],
                        'user_b_name': p.get('name', 'Comrade').split(' ')[0],
                        'timestamp': now_eat
                    }
                    proposal_ref.set(proposal_data)
                    created_proposal = proposal_data
                else:
                    created_proposal = existing
                
                # Emit SocketIO real-time alert to the nearby comrade
                try:
                    from flask import current_app
                    socketio = current_app.extensions.get('socketio')
                    if socketio:
                        socketio.emit('receive_notification', {
                            'title': '📍 Comrade Nearby!',
                            'message': f'A premium opposite-sex comrade is within 1 KM! Would you like to meet up and physically talk?',
                            'type': 'success'
                        }, room=p_id)
                except Exception as se:
                    logger.error(f"Failed to emit proximity meetup notification: {se}")
                    
        return jsonify({
            'success': True,
            'message': f'Location updated. Detected {nearby_count} premium opposite-gender comrades within 1 KM.',
            'nearby_count': nearby_count,
            'proposal': created_proposal
        })
        
    except Exception as e:
        logger.error(f"Update Location Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@v3_matching_bp.route('/location/meetup-vote', methods=['POST'])
@requires_diamond_subscription_api
def proximity_meetup_vote():
    """
    Handles a user's decision to meet up and physically talk with a nearby classmate.
    If both approve, dispatches an email containing the profiles and photos of all paid users within a 1 KM radius.
    """
    current_user_id = session.get('user_id')
    data = request.json or {}
    proposal_id = data.get('proposal_id')
    vote = data.get('vote') # 'approved' or 'declined'
    
    if not proposal_id or vote not in ['approved', 'declined']:
        return jsonify({'success': False, 'message': 'Missing proposal_id or invalid vote.'}), 400
        
    try:
        proposal_ref = db.reference(f'proximity_proposals/{proposal_id}')
        proposal = proposal_ref.get()
        
        if not proposal:
            return jsonify({'success': False, 'message': 'Proximity proposal not found.'}), 404
            
        user_role = None
        if proposal.get('user_a_id') == current_user_id:
            user_role = 'user_a'
        elif proposal.get('user_b_id') == current_user_id:
            user_role = 'user_b'
            
        if not user_role:
            return jsonify({'success': False, 'message': 'You are not a participant in this proposal.'}), 403
            
        # Update vote
        proposal_ref.update({f'{user_role}_status': vote})
        
        # Re-fetch proposal to see if both are approved
        updated_proposal = proposal_ref.get()
        status_a = updated_proposal.get('user_a_status')
        status_b = updated_proposal.get('user_b_status')
        
        if status_a == 'approved' and status_b == 'approved':
            # BOTH AGREED TO MEET AND TALK! ❤️ Reveal matches within 1 KM radius via Email
            user_a_id = updated_proposal.get('user_a_id')
            user_b_id = updated_proposal.get('user_b_id')
            
            # Fetch profiles and coords
            profile_a = db.reference(f'profiles/{user_a_id}').get() or {}
            profile_b = db.reference(f'profiles/{user_b_id}').get() or {}
            
            loc_a = profile_a.get('location') or {}
            lat_a = float(loc_a.get('latitude', 0))
            lng_a = float(loc_a.get('longitude', 0))
            
            loc_b = profile_b.get('location') or {}
            lat_b = float(loc_b.get('latitude', 0))
            lng_b = float(loc_b.get('longitude', 0))
            
            all_profiles = get_all_profiles()
            
            # Helper to retrieve nearby matches for each user
            def get_nearby_for_user(user_lat, user_lng, user_gender, user_uid):
                nearby_list = []
                for p in all_profiles:
                    p_id = p.get('id')
                    p_gender = str(p.get('gender', '')).strip().lower()
                    
                    if p_id == user_uid or not p.get('is_paid') or not p.get('is_visible', True):
                        continue
                        
                    if user_gender and p_gender and user_gender == p_gender:
                        continue
                        
                    p_loc = p.get('location') or {}
                    p_lat = p_loc.get('latitude')
                    p_lng = p_loc.get('longitude')
                    
                    if p_lat is None or p_lng is None:
                        continue
                        
                    d = calculate_distance(user_lat, user_lng, float(p_lat), float(p_lng))
                    if d <= 1.0: # 1 KM
                        score = p.get('ai_score', random.randint(65, 80))
                        nearby_list.append({
                            'id': p_id,
                            'name': p.get('name', 'Student').split(' ')[0],
                            'img': p.get('img', '/static/img/placeholder.png'),
                            'course': p.get('course', p.get('major', 'Comrade')),
                            'institution': p.get('institution_name', 'MMUST'),
                            'compatibility': score,
                            'phone': p.get('phone', '254700000000'),
                            'email': p.get('email', 'student@campus.ac.ke'),
                            'bio': p.get('bio', 'Looking for a compatibility match.')
                        })
                return nearby_list
                
            nearby_a = get_nearby_for_user(lat_a, lng_a, profile_a.get('gender', '').strip().lower(), user_a_id)
            nearby_b = get_nearby_for_user(lat_b, lng_b, profile_b.get('gender', '').strip().lower(), user_b_id)
            
            # Send emails
            from app.email_service import send_proximity_meetup_email
            
            if profile_a.get('email'):
                send_proximity_meetup_email(profile_a.get('email'), profile_a.get('name', 'Comrade'), nearby_a)
            if profile_b.get('email'):
                send_proximity_meetup_email(profile_b.get('email'), profile_b.get('name', 'Comrade'), nearby_b)
                
            # Socket Alerts
            try:
                from flask import current_app
                socketio = current_app.extensions.get('socketio')
                if socketio:
                    socketio.emit('receive_notification', {
                        'title': '🤝 Meetup Agreed!',
                        'message': 'Both of you agreed to meet! Check your email for profiles and pictures of nearby matches!',
                        'type': 'success'
                    }, room=user_a_id)
                    socketio.emit('receive_notification', {
                        'title': '🤝 Meetup Agreed!',
                        'message': 'Both of you agreed to meet! Check your email for profiles and pictures of nearby matches!',
                        'type': 'success'
                    }, room=user_b_id)
            except Exception as se:
                logger.error(f"Failed to emit meetup agree sockets: {se}")
                
            return jsonify({'success': True, 'agreed': True, 'message': '🤝 Proximity meetup agreed! Both users have been emailed nearby profiles and images.'})
            
        return jsonify({'success': True, 'agreed': False, 'message': 'Vote recorded successfully. Waiting for other comrade to respond.'})
        
    except Exception as e:
        logger.error(f"Meetup Vote Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@v3_matching_bp.route('/location/proposal-status', methods=['GET'])
@requires_diamond_subscription_api
def get_location_proposal_status():
    """
    Checks if there is a pending meetup proposal from someone nearby for the logged-in user.
    """
    current_user_id = session.get('user_id')
    try:
        proposals = db.reference('proximity_proposals').get() or {}
        
        for p_id, p_data in proposals.items():
            if not isinstance(p_data, dict):
                continue
                
            user_a = p_data.get('user_a_id')
            user_b = p_data.get('user_b_id')
            
            # Check if this user is a participant
            if current_user_id == user_a or current_user_id == user_b:
                user_role = 'user_a' if current_user_id == user_a else 'user_b'
                partner_role = 'user_b' if current_user_id == user_a else 'user_a'
                
                # Only return if the current user has NOT voted yet and the proposal is fresh
                if p_data.get(f'{user_role}_status') == 'pending':
                    return jsonify({
                        'success': True,
                        'has_proposal': True,
                        'proposal_id': p_id,
                        'partner_name': p_data.get(f'{partner_role}_name', 'Nearby Comrade')
                    })
                    
        return jsonify({'success': True, 'has_proposal': False})
    except Exception as e:
        logger.error(f"Proposal Status Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
