import os
import sys
import logging
import math
from collections import defaultdict
from typing import List

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure Python can find your app folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    from app.database import get_all_swipes
except ImportError:
    logger.error("Failed to import database modules. Running in standalone/mock mode.")
    def get_all_swipes(): return []

def get_recommendations(target_user_id: str, limit: int = 5) -> List[str]:
    """
    Highly optimized recommendation engine using pure Python Cosine Similarity.
    Eliminates dependencies on pandas and scikit-learn for memory-restricted production environments.
    """
    swipes = get_all_swipes()
    if not swipes:
        return []

    # 1. Build the User-Item matrix mapping using a nested dictionary
    # user_matrix[user_id][target_id] = score (like = 1, pass = -1)
    user_matrix = defaultdict(dict)
    
    # Track which users target has already seen/swiped on
    seen_ids = set()
    
    for swipe in swipes:
        uid = swipe.get('user_id')
        tid = swipe.get('target_id')
        action = swipe.get('action')
        
        if not uid or not tid or not action:
            continue
            
        score = 1 if action.lower() == 'like' else -1
        user_matrix[uid][tid] = score
        
        if uid == target_user_id:
            seen_ids.add(tid)

    if target_user_id not in user_matrix:
        logger.info(f"New user {target_user_id} has no swipe history.")
        return []

    # The set of seen_ids should also include the user themselves to prevent self-recommendation
    seen_ids.add(target_user_id)

    target_vector = user_matrix[target_user_id]
    
    # Calculate magnitude of target user vector
    target_mag = math.sqrt(sum(val ** 2 for val in target_vector.values()))
    if target_mag == 0:
        return []

    similarities = {}
    
    # 2. Compute Cosine Similarity between target_vector and other users' vectors
    for other_user_id, other_vector in user_matrix.items():
        if other_user_id == target_user_id:
            continue
            
        # Dot product
        dot_product = 0.0
        for item, score in target_vector.items():
            if item in other_vector:
                dot_product += score * other_vector[item]
                
        if dot_product <= 0:
            continue  # Only keep users with a positive correlation (>0)
            
        # Magnitude of other vector
        other_mag = math.sqrt(sum(val ** 2 for val in other_vector.values()))
        if other_mag == 0:
            continue
            
        similarity = dot_product / (target_mag * other_mag)
        if similarity > 0:
            similarities[other_user_id] = similarity

    if not similarities:
        return []

    # 3. Weighted Scoring (Collaborative Filtering)
    # Find items liked by similar users that target has not seen
    recommendation_rank = defaultdict(float)
    
    for other_user_id, similarity in similarities.items():
        other_vector = user_matrix[other_user_id]
        for item, score in other_vector.items():
            # Only count positive interactions (Likes) and skip seen/self profiles
            if score > 0 and item not in seen_ids:
                recommendation_rank[item] += similarity * score

    # 4. Final Filtering & Sorting
    # Sort candidates by aggregate score (descending)
    sorted_candidates = sorted(
        [(item, score) for item, score in recommendation_rank.items() if score > 0],
        key=lambda x: x[1],
        reverse=True
    )
    
    top_matches = [item for item, score in sorted_candidates[:limit]]
    return top_matches

if __name__ == "__main__":
    print("\n🚀 [MMUST AI] Recommender Engine Active (Pure Python Mode)")
    # Simulate a run
    user_to_test = "MMUST_STUDENT_X"
    suggestions = get_recommendations(user_to_test)
    
    if suggestions:
        print(f"✨ Recommended for you: {suggestions}")
    else:
        print("💡 Not enough data yet. Swipe more to train your personal AI!")