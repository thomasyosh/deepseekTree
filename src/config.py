import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_LOCALHOST_NO_PROXY = (
    "localhost",
    "127.0.0.1",
    "[::1]",
    "<local>",
    "*.local",
)


def _ensure_localhost_bypasses_proxy() -> None:
    """Keep local Ollama calls off the corporate proxy."""
    existing = os.getenv("NO_PROXY") or os.getenv("no_proxy") or ""
    hosts = {h.strip() for h in existing.replace(";", ",").split(",") if h.strip()}
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


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Explicitly disable proxy for local services (e.g. Ollama on localhost).
NO_PROXY: dict[str, None] = {"http": None, "https": None}

DATA_PATH = ROOT / "data.json"
REPORT_PATH = ROOT / "report.html"

ENDPOINT = os.getenv("ENDPOINT")
API_KEY = os.getenv("API_KEY")
PROXY = os.getenv("PROXY")
VERIFY_SSL = _env_bool("VERIFY_SSL", default=True)

# Local DeepSeek via Ollama (requests + proxies disabled for localhost)
LLM_PROVIDER = (os.getenv("LLM_PROVIDER") or "ollama").strip().lower()

AI_MODEL = os.getenv("AI_MODEL", "deepseek-r1:14b")
CHAT_MODEL = os.getenv("CHAT_MODEL") or AI_MODEL
REPORT_MODEL = os.getenv("REPORT_MODEL") or AI_MODEL

# Legacy URLs (derived from OLLAMA_BASE_URL)
_ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_BASE_URL = _ollama_base
OLLAMA_URL = os.getenv("OLLAMA_URL") or f"{_ollama_base}/v1/chat/completions"

_ollama_parts = urlparse(_ollama_base if "://" in _ollama_base else f"http://{_ollama_base}")
OLLAMA_HOST = _ollama_parts.hostname or "localhost"
OLLAMA_PORT = _ollama_parts.port or 11434
OLLAMA_PATH = "/api/chat"
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "600"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "1024"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
CHAT_CONNECT_TIMEOUT = int(os.getenv("CHAT_CONNECT_TIMEOUT", "15"))
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "300"))
CHAT_MAX_TOKENS = int(os.getenv("CHAT_MAX_TOKENS", "512"))
OLLAMA_WARMUP = _env_bool("OLLAMA_WARMUP", default=True)
REFRESH_REPORT_ON_CHAT = _env_bool("REFRESH_REPORT_ON_CHAT", default=False)
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

if not VERIFY_SSL:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
