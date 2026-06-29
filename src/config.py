import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_LOCALHOST_NO_PROXY = ("localhost", "127.0.0.1", "[::1]")


def _ensure_localhost_bypasses_proxy() -> None:
    """Keep local Ollama calls off the corporate proxy."""
    existing = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    hosts = {h.strip() for h in existing.split(",") if h.strip()}
    if set(_LOCALHOST_NO_PROXY).issubset(hosts):
        return
    merged = ",".join(sorted(hosts | set(_LOCALHOST_NO_PROXY)))
    os.environ["NO_PROXY"] = merged
    os.environ["no_proxy"] = merged


_ensure_localhost_bypasses_proxy()


def parse_proxy(proxy_value: str | None) -> dict[str, str] | None:
    if not proxy_value:
        return None
    return {"http": proxy_value, "https": proxy_value}


# Explicitly disable proxy for local services (e.g. Ollama on localhost).
NO_PROXY: dict[str, None] = {"http": None, "https": None}

DATA_PATH = ROOT / "data.json"
REPORT_PATH = ROOT / "report.html"

ENDPOINT = os.getenv("ENDPOINT")
API_KEY = os.getenv("API_KEY")
PROXY = os.getenv("PROXY")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-r1:7b")
CHAT_MODEL = os.getenv("CHAT_MODEL") or AI_MODEL
REPORT_MODEL = os.getenv("REPORT_MODEL") or AI_MODEL
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "60"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "256"))
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
