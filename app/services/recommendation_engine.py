import importlib
from app.database import get_all_profiles, get_all_feedback
from app.services.vector_search import calculate_vector_similarity

# Import the specific ML models dynamically
sched = importlib.import_module('ml_pipeline.2_schedule_sync.availability')
get_schedule_matches = sched.get_schedule_matches

cf = importlib.import_module('ml_pipeline.4_collaborative_filtering.trainer')
get_recommendations = cf.get_recommendations

def generate_ranked_deck(current_user_id):
    """
    Fetches all profiles, applies the user's Discovery Settings (Hard Filters),
    and then ranks the remaining profiles using the AI Scoring Engine.
    """
    all_profiles = get_all_profiles()
    if not all_profiles:
        return []

    # 1. Grab the current user and their specific settings
    current_user = next((p for p in all_profiles if p.get('id') == current_user_id), None)
    if not current_user:
        return []

    # Safely extract settings (with fallbacks if they haven't visited the settings page yet)
    settings = current_user.get('settings', {})
    looking_for = settings.get('looking_for', 'Everyone')
    major_filter = settings.get('major_filter', 'All')
    strict_schedule = settings.get('strict_schedule', False)
    
    # Safely extract biological data
    my_gender = current_user.get('gender')
    my_age = int(current_user.get('age', 18))

    # 2. Fetch ML Predictions & Real-World Data
    cf_recs = get_recommendations(current_user_id) 
    schedule_matches = get_schedule_matches(current_user_id) 
    all_feedback = get_all_feedback()

    successful_date_ids = [
        f['target_id'] for f in all_feedback 
        if f.get('user_id') == current_user_id and f.get('vibe_rating') == 'romantic'
    ]

    my_vibe_vector = current_user.get('vibe_vector')
    scored_profiles = []

    # 3. FILTER AND SCORE THE DECK
    for profile in all_profiles:
        # Prevent the user from matching with themselves
        if profile.get('id') == current_user_id:
            continue

        # ==========================================
        # STAGE 1: HARD FILTERS (Discovery & Biology)
        # ==========================================
        target_gender = profile.get('gender')
        target_age = int(profile.get('age', 18))

        # A. Strict Gender Filter (No Same-Sex matching based on your rules)
        if my_gender and target_gender and my_gender == target_gender:
            continue 

        # B. Strict Age Gap Filter (University Safe)
        # Everyone must be 18 or older. No exceptions.
        if target_age < 18:
            continue

        if my_gender == 'Male':
            # Men see ladies 3-5 years younger. 
            # If the man is 20, 3 years younger is 17 (illegal). 
            # We use max(18, ...) to ensure the youngest he sees is 18, even if the gap is smaller.
            min_allowed_age = max(18, my_age - 5)
            if target_age < min_allowed_age or target_age >= my_age:
                continue
                
        elif my_gender == 'Female':
            # Ladies see men 3 to 5 years older
            if not (my_age + 3 <= target_age <= my_age + 5):
                continue

        # C. KINSHIP & INCEST PREVENTION
        my_father = current_user.get('father_hash')
        my_mother = current_user.get('mother_hash')
        their_father = profile.get('father_hash')
        their_mother = profile.get('mother_hash')

        # If both users provided family data, check for exact hash matches
        if my_father and their_father and (my_father == their_father):
            continue # Drop from deck: They likely share a father
            
        if my_mother and their_mother and (my_mother == their_mother):
            continue # Drop from deck: They likely share a mother

        # D. Strict Schedule Check
        if strict_schedule and profile.get('id') not in schedule_matches:
            continue 
            
        # E. Major Filter Check 
        if major_filter != 'All':
            bio_lower = profile.get('bio', '').lower()
            
            if major_filter == 'CS_IT' and not any(kw in bio_lower for kw in ['computer', 'it', 'tech', 'software', 'code']):
                continue
            elif major_filter == 'Health' and not any(kw in bio_lower for kw in ['nurs', 'health', 'med', 'clinic']):
                continue
            elif major_filter == 'Engineering' and 'engin' not in bio_lower:
                continue
            elif major_filter == 'Business' and not any(kw in bio_lower for kw in ['busin', 'econ', 'commerce', 'finance']):
                continue
            elif major_filter == 'Education' and 'educat' not in bio_lower:
                continue

        # ==========================================
        # STAGE 2: THE AI SCORING ENGINE
        # ==========================================
        score = 0.0
        target_vibe_vector = profile.get('vibe_vector')
        
        # FEATURE A: Collaborative Filtering (+50 pts)
        if profile.get('id') in cf_recs:
            score += 50
            
        # FEATURE B: Schedule Overlap (+30 pts)
        if profile.get('id') in schedule_matches:
            score += 30
            profile['bio'] = "🕒 MATCHING FREE TIME! " + profile.get('bio', '')
            
        # FEATURE C: Computer Vision Vibe Matching (+20 pts)
        if my_vibe_vector and target_vibe_vector:
            vibe_similarity = calculate_vector_similarity(my_vibe_vector, target_vibe_vector)
            score += (vibe_similarity * 20) 

        # THE HOLY GRAIL: Real-World Lookalike Boost (+200 pts)
        for past_success_id in successful_date_ids:
            past_success_profile = next((p for p in all_profiles if p.get('id') == past_success_id), None)
            if past_success_profile and target_vibe_vector and past_success_profile.get('vibe_vector'):
                similarity = calculate_vector_similarity(past_success_profile['vibe_vector'], target_vibe_vector)
                
                if similarity > 0.85: 
                    score += 200
                    profile['bio'] = "✨ AI Top Pick (Based on your past dates!) - " + profile.get('bio', '')
                    break 
            
        profile['ai_score'] = round(score, 2)
        scored_profiles.append(profile)
        
    # 4. Sort the filtered deck from highest AI score to lowest
    ranked_profiles = sorted(scored_profiles, key=lambda x: x['ai_score'], reverse=True)
    
    return ranked_profiles