import os
from dotenv import load_dotenv
load_dotenv()
from groq import Groq

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
print(f"Key loaded: {bool(GROQ_API_KEY)}")

try:
    client = Groq(api_key=GROQ_API_KEY)
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": "hello"}],
        model="openai/gpt-oss-20b",
        max_tokens=15,
    )
    print("Response:", chat_completion.choices[0].message.content)
except Exception as e:
    print(f"Error: {e}")
