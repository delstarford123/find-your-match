import os
import logging
import torch
from PIL import Image, UnidentifiedImageError
from transformers import CLIPProcessor, CLIPModel

# 1. Configure Production Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ImageVibeExtractor:
    """
    Singleton wrapper for CLIP (Contrastive Language-Image Pre-training).
    Uses lazy-loading to keep memory footprint low until first use.
    """
    def __init__(self, model_id: str = "openai/clip-vit-base-patch32"):
        self.model_id = model_id
        self.device = self._get_device()
        self.model = None
        self.processor = None

    def _get_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        elif torch.backends.mps.is_available():
            return "mps" # Native Apple Silicon support
        return "cpu"

    def load_model(self):
        """Loads weights only when needed. Essential for limited-RAM environments like Render."""
        if self.model is None:
            logger.info(f"🚀 Initializing CLIP Model on [{self.device.upper()}]...")
            try:
                # We use the 'base' model to balance accuracy and speed
                self.model = CLIPModel.from_pretrained(self.model_id).to(self.device)
                self.processor = CLIPProcessor.from_pretrained(self.model_id)
                self.model.eval() 
                logger.info("✅ CLIP loaded and ready for feature extraction.")
            except Exception as e:
                logger.error(f"❌ CLIP Initialization Error: {e}")
                raise

    def extract_vibe(self, image_path: str) -> list | None:
        """
        Converts an image into a 512-dim normalized vector for aesthetic matchmaking.
        """
        if self.model is None:
            self.load_model()

        try:
            # Normalize image to RGB to handle PNGs/JPEGs consistently
            with Image.open(image_path) as img:
                image = img.convert("RGB")
                
                # Processor handles resizing and color normalization automatically
                inputs = self.processor(images=image, return_tensors="pt").to(self.device)
                
                with torch.no_grad(): 
                    image_features = self.model.get_image_features(**inputs)
                    
                # IMPORTANT: L2 Normalization
                # This makes Cosine Similarity (A·B) identical to simple Euclidean distance math
                image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
                
                # Move to CPU and convert to standard Python list for database storage
                vector = image_features.squeeze().cpu().tolist()
                
                # Cleanup GPU/RAM overhead immediately
                if self.device == "cuda":
                    del inputs, image_features
                    torch.cuda.empty_cache()
                    
                return vector

        except (FileNotFoundError, UnidentifiedImageError) as e:
            logger.error(f"Image Error: {e}")
            return None
        except Exception as e:
            logger.error(f"Aesthetic extraction failed: {e}")
            return None

# Exported instance for use across the Flask app
_vibe_extractor = ImageVibeExtractor()

def extract_image_vibe(image_path: str) -> list | None:
    """Centralized function for profile photo analysis."""
    return _vibe_extractor.extract_vibe(image_path)

if __name__ == "__main__":
    print("\n--- MMUST Aesthetic Matcher Test ---")
    # Simulation: Replace with actual path for local testing
    mock_path = "test_pic.jpg"
    if not os.path.exists(mock_path):
        Image.new('RGB', (224, 224), color='maroon').save(mock_path)
    
    result = extract_image_vibe(mock_path)
    if result:
        print(f"✅ Extracted vector of length {len(result)}")
        print(f"Sample: {result[:3]}...")