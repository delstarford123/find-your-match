import os
import torch
from datasets import load_dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer

# ==========================================
# 1. CONFIGURATION & PATHS
# ==========================================
# We use TinyLlama because it is only 1.1B parameters (small enough to not explode your RAM)
MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0" 

# Paths mapping to your directory structure
DATA_PATH = os.path.join(os.path.dirname(__file__), '../data/raw/text_conversations/custom_companion.jsonl')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '../models/llm_weights/companion_v1')

def format_chat_template(example):
    """
    Hugging Face needs to know how to structure the conversation.
    This takes your JSONL data and applies the standard ChatML formatting.
    """
    messages = example['messages']
    text = ""
    for msg in messages:
        if msg['role'] == 'system':
            text += f"<|system|>\n{msg['content']}</s>\n"
        elif msg['role'] == 'user':
            text += f"<|user|>\n{msg['content']}</s>\n"
        elif msg['role'] == 'assistant':
            text += f"<|assistant|>\n{msg['content']}</s>\n"
    
    return {"text": text}

def train():
    print("🚀 Initializing AI Training Pipeline...")

    # ==========================================
    # 2. LOAD DATASET
    # ==========================================
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Cannot find dataset at {DATA_PATH}. Did you create the JSONL file?")
        
    print("📚 Loading dataset...")
    dataset = load_dataset("json", data_files=DATA_PATH, split="train")
    
    # Apply our formatting function to the dataset
    dataset = dataset.map(format_chat_template)

    # ==========================================
    # 3. LOAD TOKENIZER & MODEL
    # ==========================================
    print(f"🧠 Loading base model: {MODEL_ID}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    tokenizer.pad_token = tokenizer.eos_token # Essential for batching text
    
    # Load the model. We force it to use CPU by omitting device_map="auto" and quantization
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float32, # Standard precision for CPU
        device_map="cpu"           # Explicitly telling it to run on CPU
    )

    # ==========================================
    # 4. SET UP LoRA (Low-Rank Adaptation)
    # This prevents the CPU/RAM from exploding by only training a tiny fraction of the model
    # ==========================================
    peft_config = LoraConfig(
        r=8, 
        lora_alpha=16, 
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj"] # Target attention layers
    )
    
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters() # This will show you are only training ~1% of the model!

    # ==========================================
    # 5. TRAINING ARGUMENTS (CPU OPTIMIZED)
    # ==========================================
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=1,    # Keep at 1 for CPU to save RAM
        gradient_accumulation_steps=4,    # Simulates a larger batch size
        learning_rate=2e-4,
        logging_steps=5,
        max_steps=50,                     # Keep incredibly low just to test if the CPU works
        save_steps=25,
        use_cpu=True,                     # Force Hugging Face to use CPU
        optim="adamw_torch",
        report_to="none"                  # Disable wandb tracking for now
    )

    # ==========================================
    # 6. START THE TRAINER
    # ==========================================
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        dataset_text_field="text", # The field we created in format_chat_template
        max_seq_length=512,        # Keep context window small for CPU
        tokenizer=tokenizer,
        args=training_args,
    )

    print("🔥 Starting Training! (Warning: On a CPU, this could take a very long time...)")
    trainer.train()

    # ==========================================
    # 7. SAVE THE FINE-TUNED MODEL
    # ==========================================
    print(f"✅ Training complete. Saving to {OUTPUT_DIR}...")
    trainer.model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print("🎉 Model saved successfully!")

if __name__ == "__main__":
    train()