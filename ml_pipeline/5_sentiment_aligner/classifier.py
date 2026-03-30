import os
import logging
import torch
from transformers import pipeline
from typing import List, Union

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SentimentAligner:
    """
    NLP Sentiment Pipeline for vibe-matching.
    Uses 'roberta-base-sentiment' which is highly accurate for social/dating text.
    """
    def __init__(self, model_name: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"):
        self.model_name = model_name
        # 0 = GPU, -1 = CPU. Most Render/PythonAnywhere instances will be -1.
        self.device = 0 if torch.cuda.is_available() else -1
        self.pipeline = None

    def load_model(self):
        if self.pipeline is None:
            logger.info(f"🚀 Loading Sentiment Engine on {'GPU' if self.device == 0 else 'CPU'}...")
            try:
                self.pipeline = pipeline(
                    "sentiment-analysis", 
                    model=self.model_name, 
                    tokenizer=self.model_name,
                    device=self.device,
                    truncation=True,
                    max_length=512
                )
                logger.info("✅ Sentiment Engine Ready.")
            except Exception as e:
                logger.error(f"❌ Sentiment model load failed: {e}")
                raise

    def get_scores(self, texts: Union[str, List[str]]) -> Union[float, List[float]]:
        """
        Analyzes one or many strings. 
        Returns score from -1.0 (Negative) to +1.0 (Positive).
        """
        if not texts:
            return 0.0 if isinstance(texts, str) else []
            
        if self.pipeline is None:
            self.load_model()
            
        input_list = [texts] if isinstance(texts, str) else texts
        
        try:
            results = self.pipeline(input_list)
            scores = []
            
            for res in results:
                label = res['label'].lower()
                conf = res['score']
                
                # Logic: Positive = 0 to 1, Negative = -1 to 0, Neutral = 0
                if 'positive' in label:
                    scores.append(round(conf, 4))
                elif 'negative' in label:
                    scores.append(round(-conf, 4))
                else:
                    scores.append(0.0)

            return scores[0] if isinstance(texts, str) else scores

        except Exception as e:
            logger.error(f"Sentiment Analysis Failure: {e}")
            return 0.0 if isinstance(texts, str) else [0.0] * len(input_list)

    def calculate_alignment(self, score_a: float, score_b: float) -> float:
        """
        Linear Alignment Scoring.
        1.0 = Perfectly Aligned Vibe
        0.0 = Total Vibe Clash
        """
        # abs(1.0 - (-1.0)) = 2.0 (Max distance)
        # abs(0.5 - 0.6) = 0.1 (Close distance)
        distance = abs(score_a - score_b)
        
        # Scale to 0.0 - 1.0
        alignment = 1.0 - (distance / 2.0)
        
        # MMUST Bias: If both are neutral (0.0), they are technically aligned.
        return round(alignment, 2)

# Singleton Export
_aligner = SentimentAligner()

def get_sentiment_score(text: str) -> float:
    return _aligner.get_scores(text)

def get_batch_scores(texts: List[str]) -> List[float]:
    return _aligner.get_scores(texts)

def calculate_compatibility(s1: float, s2: float) -> float:
    return _aligner.calculate_alignment(s1, s2)

if __name__ == "__main__":
    print("\n--- MMUST Sentiment Engine Test ---")
    
    # Example: A 'hot take' on MMUST food or classes
    t1 = "I absolutely hate morning lectures, they ruin my vibe."
    t2 = "Morning classes are the worst! I'm a night owl."
    t3 = "I love getting up early and being productive at the MCU."
    
    s1, s2, s3 = get_batch_scores([t1, t2, t3])
    
    print(f"Alignment (1 & 2): {calculate_compatibility(s1, s2)} (Should be High)")
    print(f"Alignment (1 & 3): {calculate_compatibility(s1, s3)} (Should be Low)")