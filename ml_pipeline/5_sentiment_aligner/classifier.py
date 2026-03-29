import os
import logging
import torch
from transformers import pipeline

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SentimentAligner:
    """
    Lazy-loading wrapper for the NLP Sentiment Pipeline.
    Prevents memory hogging and provides mathematically sound alignment scoring.
    """
    def __init__(self, model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"):
        self.model_name = model_name
        # PyTorch pipelines use 0 for the first GPU, and -1 for CPU
        self.device_id = 0 if torch.cuda.is_available() else -1
        self.pipeline = None

    def load_model(self):
        """Loads the weights into RAM/VRAM only when actually needed."""
        if self.pipeline is None:
            logger.info(f"Loading NLP Sentiment Model on {'GPU' if self.device_id == 0 else 'CPU'}...")
            try:
                self.pipeline = pipeline(
                    "sentiment-analysis", 
                    model=self.model_name, 
                    tokenizer=self.model_name,
                    device=self.device_id,
                    truncation=True,    # Prevents app crash if text is too long
                    max_length=512      # Caps input size to model limits
                )
                logger.info("✅ NLP Sentiment Model loaded successfully!")
            except Exception as e:
                logger.error(f"❌ Failed to load Sentiment model: {e}")
                raise

    def get_sentiment_score(self, text: str) -> float:
        """
        Analyzes text and returns a float score between -1.0 (Negative) and +1.0 (Positive).
        """
        if not text or not isinstance(text, str):
            return 0.0
            
        if self.pipeline is None:
            self.load_model()
            
        try:
            result = self.pipeline(text)[0]
            label = result['label'].lower()
            confidence = result['score'] 

            if 'positive' in label:
                return round(confidence, 4)
            elif 'negative' in label:
                return round(-confidence, 4)
            else:
                return 0.0 # Neutral

        except Exception as e:
            logger.error(f"Sentiment Analysis Error on text '{text[:20]}...': {e}")
            return 0.0

    def calculate_alignment(self, score_a: float, score_b: float) -> float:
        """
        Calculates true compatibility on a 0.0 to 1.0 scale (0% to 100%).
        Using Absolute Difference instead of Multiplication fixes the math logic.
        """
        # Difference ranges from 0 (identical) to 2 (polar opposites: +1 and -1)
        diff = abs(score_a - score_b)
        
        # Convert to a 0.0 - 1.0 scale where 0 difference = 1.0 (100% match)
        alignment = 1.0 - (diff / 2.0)
        
        return round(alignment, 2)


# ==========================================
# EXPORTED INSTANCE & WRAPPER FUNCTIONS
# ==========================================
# Singleton instance prevents loading the model twice
_aligner = SentimentAligner()

def get_sentiment_score(text: str) -> float:
    return _aligner.get_sentiment_score(text)

def calculate_alignment(score_a: float, score_b: float) -> float:
    return _aligner.calculate_alignment(score_a, score_b)


# --- FOR TESTING PURPOSES ---
if __name__ == "__main__":
    print("\n--- MMUST Hot Takes Matcher ---")
    
    # Text samples
    wanjiku_txt = "Absolutely not. I'd rather sleep in."
    ochieng_txt = "Never. Walking to class at 7:30 AM is the worst."
    kipchoge_txt = "Yes! It gets my day started early."
    
    # Get Scores
    w_score = get_sentiment_score(wanjiku_txt)
    o_score = get_sentiment_score(ochieng_txt)
    k_score = get_sentiment_score(kipchoge_txt)
    
    print(f"\nScores (Range -1.0 to 1.0):")
    print(f"Wanjiku  : {w_score}  ({wanjiku_txt})")
    print(f"Ochieng  : {o_score}  ({ochieng_txt})")
    print(f"Kipchoge : {k_score}  ({kipchoge_txt})")
    
    # Calculate True Alignments
    print(f"\nMatch Results (0.0 to 1.0):")
    print(f"Wanjiku + Ochieng  Compatibility: {calculate_alignment(w_score, o_score)} (Expect High)")
    print(f"Wanjiku + Kipchoge Compatibility: {calculate_alignment(w_score, k_score)} (Expect Low)")