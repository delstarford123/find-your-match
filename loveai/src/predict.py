import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ==========================================
# 1. CONFIGURATION & PATHS
# ==========================================
BASE_MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
# Path to the deep nested folder from your screenshots
MODEL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), 
    '../models/llm_weights/companion_v1/loveai/models/llm_weights/companion_v1'
))

_model = None
_tokenizer = None

def load_model():
    global _model, _tokenizer
    if _model is not None: return

    print("📚 Fetching and aligning vocabulary...")
    # Fix: Explicitly set the chat template and special tokens
    _tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID)
    _tokenizer.pad_token = _tokenizer.eos_token
    
    print(f"🧠 Loading base brain...")
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        torch_dtype=torch.float32,
        device_map="cpu"
    )
    
    print(f"🎓 Patching custom MMUST knowledge...")
    _model = PeftModel.from_pretrained(base_model, MODEL_PATH)
    _model.eval()
    print("✅ AI Companion is awake!")

def generate_response(user_text):
    global _model, _tokenizer
    if _model is None: load_model()

    # Simplest prompt format to avoid <unk> issues
    prompt = f"User: {user_text}\nAssistant:"

    inputs = _tokenizer(prompt, return_tensors="pt", add_special_tokens=True).to("cpu")

    with torch.no_grad():
        outputs = _model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            max_new_tokens=80,
            do_sample=False, # Stay Greedy for stability
            pad_token_id=_tokenizer.eos_token_id,
            eos_token_id=_tokenizer.eos_token_id
        )

    # Decode while removing the prompt itself
    full_text = _tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Extract only the part after "Assistant:"
    if "Assistant:" in full_text:
        reply = full_text.split("Assistant:")[-1].strip()
    else:
        reply = full_text.replace(prompt, "").strip()

    return reply if len(reply) > 2 else "That's a tough one, comrade. Don't let it stress you out too much!"

if __name__ == "__main__":
    load_model()
    print("\nMMUST AI COMPANION (v1.1)")
    while True:
        user_input = input("\nYou: ")
        if user_input.lower() in ['quit', 'exit']: break
        print(f"AI Companion: {generate_response(user_input)}")