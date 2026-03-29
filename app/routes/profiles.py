from flask import Blueprint, request, jsonify

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