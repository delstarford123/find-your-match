import json

def verify_data():
    path = "../data/raw/text_conversations/custom_companion.jsonl"
    try:
        with open(path, "r") as f:
            lines = f.readlines()
            print(f"🔍 Data Integrity Check: {len(lines)} samples found.")
            for i, line in enumerate(lines[:3]): # Check first 3
                data = json.loads(line)
                if "messages" in data:
                    print(f"✅ Sample {i+1} is valid.")
                else:
                    print(f"❌ Sample {i+1} is corrupted.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    verify_data()