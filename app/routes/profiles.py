import random
from flask import Blueprint, request, jsonify
from app.database import db

# Import the master recommendation engine we just built
from app.services.recommendation_engine import generate_ranked_deck

profiles_bp = Blueprint('profiles', __name__)
@profiles_bp.route('/api/profiles', methods=['GET'])
def get_profiles():
    user_id = request.args.get('user_id')
    
    if not user_id:
        return jsonify({"error": "User ID required"}), 400

    # Trigger the ML Engine
    sorted_profiles = generate_ranked_deck(user_id)
    
    # --- 💰 NATIVE AD INJECTION ---
    try:
        ads_ref = db.reference('active_ads')
        ads = ads_ref.order_by_child('status').equal_to('active').get()
        if ads:
            ad_list = []
            for k, v in ads.items():
                ad_list.append({
                    'id': k,
                    'is_ad': True,
                    'name': 'Sponsored',
                    'img': v.get('media_url'),
                    'bio': 'PROMOTED: Click to learn more about this special offer!',
                    'click_link': v.get('click_link') or v.get('target_url'),
                    'intent': 'promotion',
                    'ai_score': 99 # Ads always look like a perfect match!
                })
            
            # Inject ads every 6-10 profiles
            if sorted_profiles and len(sorted_profiles) > 3:
                # Inject first ad at position 3-5
                sorted_profiles.insert(random.randint(2, 4), random.choice(ad_list))
                
                # If deck is long, inject another one further down
                if len(sorted_profiles) > 12:
                    sorted_profiles.insert(random.randint(9, 11), random.choice(ad_list))
    except Exception as e:
        print(f"Ad injection failed: {e}")

    # 4. Graceful Empty State
    if not sorted_profiles:
        return jsonify({
            "status": "exhausted",
            "message": "You've seen everyone for now! Check back later or expand your preferences.",
            "profiles": []
        })
    
    return jsonify({
        "status": "success",
        "count": len(sorted_profiles),
        "profiles": sorted_profiles
    })