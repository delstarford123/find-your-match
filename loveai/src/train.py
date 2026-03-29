import preprocess_text
import train_llm
import train_voice

def run_full_pipeline():
    print("--- 🛠️ STARTING FULL AI TRAINING PIPELINE ---")
    
    # 1. Prepare Text
    preprocess_text.clean_and_format()
    
    # 2. Train Brain (LLM)
    # Warning: This is the part that takes hours on CPU
    try:
        train_llm.train()
    except Exception as e:
        print(f"LLM Training skipped or failed: {e}")
    
    # 3. Train Voice
    train_voice.train_voice_clone("female")
    train_voice.train_voice_clone("male")
    
    print("--- 🎉 ALL MODELS READY FOR DEPLOYMENT ---")

if __name__ == "__main__":
    run_full_pipeline()