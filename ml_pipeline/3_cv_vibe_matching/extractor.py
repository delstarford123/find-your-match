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
    A lazy-loading wrapper for the CLIP Neural Network. 
    Prevents the model from hogging RAM until it is explicitly needed.
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
            return "mps"
        return "cpu"

    def load_model(self):
        """Loads the weights into memory only when called."""
        if self.model is None:
            logger.info(f"Loading Vision Model '{self.model_id}' on [{self.device.upper()}]... This might take a moment.")
            try:
                self.model = CLIPModel.from_pretrained(self.model_id).to(self.device)
                self.processor = CLIPProcessor.from_pretrained(self.model_id)
                self.model.eval() # CRITICAL: Sets model to inference mode (disables dropout layers)
                logger.info("✅ Vision Model loaded successfully!")
            except Exception as e:
                logger.error(f"❌ Failed to load CLIP model: {e}")
                raise

    def extract_vibe(self, image_path: str) -> list | None:
        """
        Runs an image through CLIP and returns a 512-dimensional normalized vector.
        """
        # Lazy load: Only boot up the AI if it hasn't been loaded yet
        if self.model is None:
            self.load_model()

        try:
            # Using 'with' ensures the file is safely closed after reading, preventing file lock errors
            with Image.open(image_path) as img:
                image = img.convert("RGB")
            
            inputs = self.processor(images=image, return_tensors="pt").to(self.device)
            
            with torch.no_grad(): 
                image_features = self.model.get_image_features(**inputs)
                
            # Normalize the vector (essential for Cosine Similarity matchmaking later)
            image_features = image_features / image_features.norm(p=2, dim=-1, keepdim=True)
            
            # Squeeze and convert to a standard Python list
            vector = image_features.squeeze().cpu().tolist()
            
            # Memory Cleanup: Free up the GPU memory immediately after processing
            if self.device == "cuda":
                del inputs, image_features
                torch.cuda.empty_cache()
                
            return vector

        except FileNotFoundError:
            logger.error(f"Image not found at path: {image_path}")
            return None
        except UnidentifiedImageError:
            logger.error(f"File at {image_path} is not a valid image format.")
            return None
        except Exception as e:
            logger.error(f"Unexpected error processing image {image_path}: {e}")
            return None

# ==========================================
# EXPORTED INSTANCE & WRAPPER FUNCTION
# ==========================================
# We create a singleton instance so the model isn't duplicated across your app
_vibe_extractor = ImageVibeExtractor()

def extract_image_vibe(image_path: str) -> list | None:
    """Wrapper function to maintain compatibility with your existing import statements."""
    return _vibe_extractor.extract_vibe(image_path)


# --- FOR TESTING PURPOSES ---
if __name__ == "__main__":
    print("\n--- MMUST Image Vibe Extractor ---")
    test_image_dir = os.path.join(os.path.dirname(__file__), '../../data/raw_images')
    os.makedirs(test_image_dir, exist_ok=True)
    test_image_path = os.path.join(test_image_dir, 'test_profile.jpg')
    
    # Create a dummy image if one doesn't exist
    if not os.path.exists(test_image_path):
        img = Image.new('RGB', (400, 400), color='red')
        img.save(test_image_path)
        logger.info(f"Created mock test image at {test_image_path}")

    vibe_vector = extract_image_vibe(test_image_path)
    
    if vibe_vector:
        print(f"\n✅ Success! Extracted a {len(vibe_vector)}-dimensional 'vibe' vector.")
        print(f"First 5 numbers: {vibe_vector[:5]}")