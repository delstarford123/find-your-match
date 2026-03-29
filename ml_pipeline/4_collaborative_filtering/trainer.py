import os
import sys
import logging
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ensure Python can find your app folder
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

try:
    from app.database import get_all_swipes
except ImportError:
    logger.error("Failed to import 'get_all_swipes'. Ensure you are running from the correct directory.")
    get_all_swipes = lambda: []

def load_swipe_data() -> pd.DataFrame | None:
    """Loads and sanitizes swipe data from Firebase into a Pandas DataFrame."""
    swipes_list = get_all_swipes()
    
    if not swipes_list:
        logger.info("No swipe data found in Firebase yet.")
        return None
    
    df = pd.DataFrame(swipes_list)
    
    # Guard clause: ensure required columns actually exist before processing
    required_cols = {'user_id', 'target_id', 'action'}
    if not required_cols.issubset(df.columns):
        logger.error("Swipe data from Firebase is missing required columns!")
        return None

    df = df.rename(columns={'user_id': 'user_a_id', 'target_id': 'user_b_id', 'action': 'interaction'})
    
    mapping = {'like': 1, 'pass': -1}
    df['score'] = df['interaction'].map(mapping)
    df = df.dropna(subset=['score'])
    
    return df

def get_recommendations(target_user_id: str, num_recommendations: int = 5) -> list:
    """
    Predicts profiles the target will like using Highly Optimized Matrix Math.
    """
    df = load_swipe_data()
    if df is None or df.empty:
        return [] 
    
    # 1. Create the User-Item Matrix
    user_matrix = df.pivot_table(index='user_a_id', columns='user_b_id', values='score', fill_value=0)
    
    if target_user_id not in user_matrix.index:
        logger.info(f"User {target_user_id} hasn't swiped on anyone yet. Skipping predictions.")
        return []
    
    # 2. PERFORMANCE FIX: Calculate Cosine Similarity ONLY for the target user
    # This turns an O(N^2) operation into an O(N) operation. Huge memory savings!
    target_vector = user_matrix.loc[[target_user_id]]
    similarities = cosine_similarity(target_vector, user_matrix)[0]
    
    # Map the resulting numpy array back to the user IDs
    sim_series = pd.Series(similarities, index=user_matrix.index)
    
    # 3. Filter out the target user and anyone with opposite/zero tastes
    sim_series = sim_series[(sim_series.index != target_user_id) & (sim_series > 0)]
    
    if sim_series.empty:
        return [] # No similar users found
        
    # 4. PERFORMANCE FIX: Vectorized Matrix Multiplication (No slow loops!)
    # Get the sub-matrix of ONLY the similar users
    similar_users_matrix = user_matrix.loc[sim_series.index]
    
    # Create a boolean matrix of profiles they actually liked (score > 0)
    likes_matrix = (similar_users_matrix > 0).astype(float)
    
    # Multiply their likes by their exact similarity score to our target user
    weighted_likes = likes_matrix.multiply(sim_series, axis=0)
    
    # Sum the columns to get a final recommendation score for every profile at once
    recommendation_scores = weighted_likes.sum(axis=0)
    
    # 5. Remove profiles the target user has already seen
    already_swiped = set(df[df['user_a_id'] == target_user_id]['user_b_id'].tolist())
    already_swiped.add(target_user_id) # Prevent recommending themselves
    
    # Safely drop already swiped profiles if they exist in the scoring index
    valid_recs = recommendation_scores.drop(index=list(already_swiped.intersection(recommendation_scores.index)))
    
    # Sort highest to lowest and drop profiles that scored a 0
    top_recs = valid_recs[valid_recs > 0].sort_values(ascending=False).head(num_recommendations)
    
    return top_recs.index.tolist()

if __name__ == "__main__":
    print("\n--- MMUST Collaborative Filtering Engine ---")
    test_user = 'MMUST_001'
    recs = get_recommendations(test_user)
    
    if recs:
        print(f"✅ Algorithm recommends these profiles for {test_user}: {recs}")
    else:
        print(f"❌ Not enough overlap data to make a prediction for {test_user}. Go swipe!")