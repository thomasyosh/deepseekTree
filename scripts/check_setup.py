"""Quick setup check for colleagues running Python without Docker."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import os  # noqa: E402

import config  # noqa: E402
import deepseek  # noqa: E402
import llm_client  # noqa: E402
import app2 as pipeline  # noqa: E402


def main() -> int:
    print("=== deepseekTree setup check ===\n")

    print(f"ENDPOINT set: {bool(config.ENDPOINT)}")
    print(f"OLLAMA_BASE_URL: {config.OLLAMA_BASE_URL}")
    print(f"LLM_PROVIDER: {config.LLM_PROVIDER}")
    print(f"CHAT_MODEL:   {config.CHAT_MODEL}")
    print(f"HTTP_PROXY:   {os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy') or '(not set)'}")
    print(f"NO_PROXY:     {os.environ.get('NO_PROXY') or os.environ.get('no_proxy') or '(not set)'}")
    print()

    health = llm_client.check_llm_health()
    label = "Local DeepSeek (Ollama)" if config.LLM_PROVIDER == "ollama" else "OpenAI cloud"
    if health["ok"]:
        print(f"{label}: OK")
        if config.LLM_PROVIDER == "ollama":
            print(f"  Models: {', '.join(health.get('models_available', [])) or '(none)'}")
    else:
        print(f"{label}: FAILED — {health.get('error')}")
    for hint in health["hints"]:
        print(f"  → {hint}")
    print()

    if config.ENDPOINT:
        print("Fetching data.json test...")
        if pipeline.fetch_data():
            print("Supabase fetch: OK")
        else:
            print("Supabase fetch: FAILED (check ENDPOINT, API_KEY, PROXY, VERIFY_SSL)")
    else:
        print("Supabase: skipped (ENDPOINT not set)")

    print()
    if health["ok"]:
        print("Ready. Start the server:")
        print("  uvicorn app:app --app-dir src --reload --host 127.0.0.1 --port 8000")
        return 0

    print("Fix LLM setup, then re-run: python scripts/check_setup.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
