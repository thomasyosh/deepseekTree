import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_PATH = ROOT / "data.json"
REPORT_PATH = ROOT / "report.html"

ENDPOINT = os.getenv("ENDPOINT")
API_KEY = os.getenv("API_KEY")
PROXY = os.getenv("PROXY")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-r1:8b")
CHAT_MODEL = os.getenv("CHAT_MODEL") or AI_MODEL
REPORT_MODEL = os.getenv("REPORT_MODEL") or AI_MODEL
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "60"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "256"))
