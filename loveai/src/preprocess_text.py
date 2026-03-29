import json
import os

RAW_DATA_PATH = "../data/raw/text_conversations/raw_logs.txt"
OUTPUT_PATH = "../data/raw/text_conversations/custom_companion.jsonl"

def clean_and_format():
    if not os.path.exists(RAW_DATA_PATH):
        print(f"❌ No raw logs found at {RAW_DATA_PATH}")
        return

    formatted_data = []
    
    with open(RAW_DATA_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Logic to convert raw text pairs into JSONL structure
    # This assumes a format like:
    # User: Hi
    # Assistant: Hello!
    for i in range(0, len(lines)-1, 2):
        user_line = lines[i].replace("User: ", "").strip()
        assistant_line = lines[i+1].replace("Assistant: ", "").strip()
        
        entry = {
            "messages": [
                {"role": "system", "content": "You are a supportive MMUST AI companion."},
                {"role": "user", "content": user_line},
                {"role": "assistant", "content": assistant_line}
            ]
        }
        formatted_data.append(entry)

    with open(OUTPUT_PATH, "w") as f:
        for entry in formatted_data:
            f.write(json.dumps(entry) + "\n")
            
    print(f"✅ Successfully preprocessed {len(formatted_data)} conversations!")

if __name__ == "__main__":
    clean_and_format()