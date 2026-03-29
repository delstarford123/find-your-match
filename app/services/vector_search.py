import numpy as np

def calculate_vector_similarity(vec_a, vec_b):
    """
    Calculates the mathematical distance (Cosine Similarity) between two vectors.
    Returns a float between -1.0 (Completely opposite) and 1.0 (Identical).
    """
    # If a user hasn't uploaded a photo yet, they won't have a vector
    if not vec_a or not vec_b:
        return 0.0

    # Convert standard Python lists to NumPy arrays for blazing-fast math
    a = np.array(vec_a)
    b = np.array(vec_b)

    # Execute the Cosine Similarity formula
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    # Prevent division by zero just in case a vector is totally empty
    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)