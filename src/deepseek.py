import os
import json
import requests
from dotenv import load_dotenv
import filelogger


model = os.getenv("AI_MODEL")
# 1. Read the local JSON file
with open("data.json", "r", encoding="utf-8") as file:
    local_json_data = json.load(file)

# 2. Build the request payload
payload = {
    "model": model, # Replace with your locally pulled model
    "messages": [
        {"role": "user", "content": f"Summarize this data: {json.dumps(local_json_data)}"}
    ],
    "stream": False
}

# 3. Send to the local Ollama API
response = requests.post(
    "http://localhost:11434/v1/chat/completions",
    json=payload
)

print(response.json()["choices"][0]["message"]["content"])