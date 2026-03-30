import os
import sys
import logging
import pandas as pd
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
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

def load_swipe_data() -> pd.DataFrame:
    """Fetches and cleans swipe data for the matrix engine."""
    swipes = get_all_swipes()
    if not swipes:
        return pd.DataFrame()
    
    df = pd.DataFrame(swipes)
    
    # Validation
    required = {'user_id', 'target_id', 'action'}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    # Map interactions to numerical weights
    # 'Like' = 1.0, 'Pass' = -1.0
    df['score'] = df['action'].map({'like': 1, 'pass': -1}).fillna(0)
    return df

def get_recommendations(target_user_id: str, limit: int = 5) -> List[str]:
    """
    Highly optimized recommendation engine using Vectorized Cosine Similarity.
    """
    df = load_swipe_data()
    if df.empty:
        return []

    # 1. Pivot into a User-Item Matrix (Rows: Swipers, Cols: Profiles being swiped)
    # Using 'score' as the value. fill_value=0 represents 'No interaction'
    user_matrix = df.pivot_table(index='user_id', columns='target_id', values='score', fill_value=0)

    if target_user_id not in user_matrix.index:
        logger.info(f"New user {target_user_id} has no swipe history.")
        return []

    # 2. Compute Similarity
    # We compare the target user's vector against ALL other users
    target_vector = user_matrix.loc[[target_user_id]]
    similarities = cosine_similarity(target_vector, user_matrix)[0]
    
    # Map similarity scores to user IDs
    sim_series = pd.Series(similarities, index=user_matrix.index)
    
    # Filter: Only keep users with a positive correlation (>0) and exclude self
    sim_series = sim_series[(sim_series.index != target_user_id) & (sim_series > 0)]
    
    if sim_series.empty:
        return []

    # 3. Weighted Scoring (Collaborative Filtering)
    # Find profiles liked by 'similar' users that the target hasn't seen
    similar_users_interactions = user_matrix.loc[sim_series.index]
    
    # Binary 'liked' matrix (only count positive interactions)
    likes_only = (similar_users_interactions > 0).astype(float)
    
    # Weight the likes by the similarity score of the person who gave the like
    weighted_votes = likes_only.multiply(sim_series, axis=0)
    
    # Aggregate scores for each profile
    recommendation_rank = weighted_votes.sum(axis=0)

    # 4. Final Filtering
    # Remove users the target has already interacted with
    seen_ids = set(df[df['user_id'] == target_user_id]['target_id'])
    seen_ids.add(target_user_id) # Don't recommend self
    
    # Clean up the results
    valid_candidates = recommendation_rank.drop(labels=list(seen_ids), errors='ignore')
    
    # Sort and return IDs of top picks
    top_matches = valid_candidates[valid_candidates > 0].sort_values(ascending=False).head(limit)
    
    return top_matches.index.tolist()

if __name__ == "__main__":
    print("\n🚀 [MMUST AI] Recommender Engine Active")
    # Simulate a run
    user_to_test = "MMUST_STUDENT_X"
    suggestions = get_recommendations(user_to_test)
    
    if suggestions:
        print(f"✨ Recommended for you: {suggestions}")
    else:
        print("💡 Not enough data yet. Swipe more to train your personal AI!")