import os
from dotenv import load_dotenv
from huggingface_hub import HfApi, login

# Load the secrets from your .env file
load_dotenv()

# 1. Login Securely
token = os.getenv("HF_TOKEN")

if not token:
    print("⚠️ ERROR: HF_TOKEN not found! Make sure your .env file is set up correctly.")
    exit()

login(token=token)
api = HfApi()
repo_id = "Delstarford/mmust-ai-companion-v1"

# 2. Update the Metadata to force the "Inference Provider" to turn on
try:
    api.update_repo_settings(
        repo_id=repo_id,
        inference=True,
    )
    print("🚀 Inference API forced to ON.")
except Exception as e:
    print(f"Metadata update note: {e}")

print("\n✅ GO TO YOUR BROWSER NOW:")
print(f"https://huggingface.co/{repo_id}")
print("Refresh the page and check if the 'Inference Providers' section changed!")