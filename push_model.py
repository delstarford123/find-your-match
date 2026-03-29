import os
from huggingface_hub import HfApi, login

# 1. Login using your token directly in the script
# This bypasses the need for the huggingface-cli terminal command
token = os.getenv("HF_TOKEN")
print("Logging into Hugging Face...")
login(token=token)

# 2. Set up the API
api = HfApi()

# 3. Define your Hugging Face username and the new model name
# CHANGE 'YOUR_HF_USERNAME' TO YOUR ACTUAL HUGGING FACE USERNAME!
hf_username = "Delstarford" 
model_name = "mmust-ai-companion-v1"
repo_id = f"{hf_username}/{model_name}"

print(f"🚀 Creating repository: {repo_id}...")
# exist_ok=True means it won't crash if you run this script twice
api.create_repo(repo_id=repo_id, exist_ok=True)

# 4. Point this to the folder containing your adapter_config.json and .safetensors files
# Based on your previous git logs, this is the correct path:
folder_to_upload = "loveai/models/llm_weights/companion_v1/loveai/models/llm_weights/companion_v1"

print(f"⏳ Uploading weights from '{folder_to_upload}'...")
print("This might take a few minutes depending on your internet speed.")

try:
    api.upload_folder(
        folder_path=folder_to_upload,
        repo_id=repo_id,
        repo_type="model",
    )
    print(f"✅ Success! Your model is now live at: https://huggingface.co/{repo_id}")
except Exception as e:
    print(f"❌ Upload failed. Error: {e}")
    print("Check that the 'folder_to_upload' path is exactly correct!")