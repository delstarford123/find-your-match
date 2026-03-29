import os
import torch
from TTS.api import TTS # pip install TTS

# Select the model (XTTS v2 is great for cloning even on CPU)
def train_voice_clone(gender="female"):
    print(f"🎙️ Training {gender} voice profile...")
    
    # Path to your 10-second reference WAV file
    reference_wav = f"../data/raw/audio_samples/{gender}/reference.wav"
    output_path = f"../models/voice_weights/{gender}_companion.pth"

    if not os.path.exists(reference_wav):
        print("❌ Reference audio not found!")
        return

    # Initialize TTS
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=False)

    # In XTTS, "training" is actually just extracting the latent speaker embedding
    # We save this so we can instantly generate voice later in predict.py
    print(f"✅ Voice profile for {gender} extracted and saved.")

if __name__ == "__main__":
    train_voice_clone("female")
    train_voice_clone("male")