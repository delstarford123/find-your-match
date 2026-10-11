import importlib
from app.database import get_all_profiles, get_all_feedback
from app.services.vector_search import calculate_vector_similarity

# Import the specific ML models dynamically
sched = importlib.import_module('ml_pipeline.2_schedule_sync.availability')
get_schedule_matches = sched.get_schedule_matches

cf = importlib.import_module('ml_pipeline.4_collaborative_filtering.trainer')
get_recommendations = cf.get_recommendations

def is_opposite_gender_match(my_gender, target_gender):
    """
    Enforces strict opposite-gender matching:
    - Ladies only see male profiles
    - Males only see female profiles
    """
    g1 = (my_gender or '').strip().lower()
    g2 = (target_gender or '').strip().lower()
    
    male_aliases = {'male', 'man', 'm', 'boy'}
    female_aliases = {'female', 'woman', 'f', 'lady', 'girl'}
    
    if g1 in male_aliases:
        return g2 in female_aliases
    elif g1 in female_aliases:
        return g2 in male_aliases
    elif g1 and g2:
        return g1 != g2
    return True

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
        try:
            from app.database import get_sponsor_profile
            current_user = get_sponsor_profile(current_user_id)
        except Exception:
            pass
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
        target_age = int(profile.get('age', 18) or 18)

        # A. Strict Gender Filter (Opposite-gender matching: ladies only see males, males only see females)
        if not is_opposite_gender_match(my_gender, target_gender):
            continue 

        # B. Strict Age Gap Filter (University Safe - 18+ and peer range)
        if target_age < 18:
            continue

        if abs(target_age - my_age) > 8:
            continue

        # B2. SHADOWBAN CHECK
        if profile.get('is_shadowbanned'):
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
            
        # FEATURE 1: Compatibility Score Badge
        # Calculate a user-friendly match percentage (cap at 99%)
        raw_percent = 60 + min(score / 300.0 * 39, 39)
        profile['compatibility'] = int(round(raw_percent))
        
        profile['ai_score'] = round(score, 2)
        scored_profiles.append(profile)
        
    # 4. Sort the filtered deck from highest AI score to lowest
    ranked_profiles = sorted(scored_profiles, key=lambda x: x['ai_score'], reverse=True)
    
    # 5. Safety fallback if filters produced zero matches (still strictly opposite gender)
    if not ranked_profiles and all_profiles:
        for p in all_profiles[:40]:
            if p.get('id') != current_user_id and p.get('is_visible', True):
                if is_opposite_gender_match(my_gender, p.get('gender')):
                    p_copy = dict(p)
                    p_copy['compatibility'] = 82
                    p_copy['ai_score'] = 82.0
                    ranked_profiles.append(p_copy)
                    if len(ranked_profiles) >= 10:
                        break
    
    return ranked_profiles