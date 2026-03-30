import os
from dotenv import load_dotenv

load_dotenv()

# Pull the keys securely from the .env file
HF_TOKEN = os.getenv("HF_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")