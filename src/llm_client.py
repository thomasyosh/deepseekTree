"""Local DeepSeek via Ollama using requests with proxy bypass."""
from __future__ import annotations

from typing import Any

import requests

import config
import filelogger


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    stream: bool = False,
    timeout: int | None = None,
    max_tokens: int = 1500,
) -> str:
    if stream:
        raise NotImplementedError("Streaming is not enabled in this app")

    model_name = model or config.CHAT_MODEL
    request_timeout = timeout or config.CHAT_TIMEOUT
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "num_ctx": config.OLLAMA_NUM_CTX,
        },
    }

    filelogger.logger.info(
        f"Calling Ollama model={model_name} url={url} (proxies disabled for localhost)"
    )
    response = requests.post(
        url,
        json=payload,
        proxies=config.NO_PROXY,
        timeout=request_timeout,
    )
    response.raise_for_status()
    data = response.json()
    message = data.get("message", {})
    content = message.get("content")
    if not content:
        raise RuntimeError(f"Unexpected Ollama response: {data}")
    return content


def check_llm_health(timeout: int = 5) -> dict[str, Any]:
    health: dict[str, Any] = {
        "ok": False,
        "provider": "ollama",
        "base_url": config.OLLAMA_BASE_URL,
        "model_configured": config.CHAT_MODEL,
        "models_available": [],
        "error": None,
        "hints": [],
        "proxy_bypass": config.NO_PROXY,
    }

    try:
        response = requests.get(
            f"{config.OLLAMA_BASE_URL}/api/tags",
            proxies=config.NO_PROXY,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        health["models_available"] = models
        health["ok"] = True

        if not _model_available(config.CHAT_MODEL, models):
            health["hints"].append(
                f"Model '{config.CHAT_MODEL}' not found. Run: ollama pull {config.CHAT_MODEL}"
            )
    except requests.exceptions.RequestException as e:
        health["error"] = str(e)
        health["hints"] = [
            "Install and start Ollama from https://ollama.com",
            f"Set OLLAMA_BASE_URL={config.OLLAMA_BASE_URL} in .env",
            "Pull the model: ollama pull deepseek-r1:14b",
            "Test: curl.exe --noproxy \"*\" http://localhost:11434/api/tags",
        ]
    return health


def _model_available(model: str, available: list[str]) -> bool:
    if not available:
        return False
    if model in available:
        return True
    prefix = f"{model}:"
    return any(name == model or name.startswith(prefix) for name in available)


def llm_troubleshooting_html(error: Exception | None = None) -> str:
    from deepseek import ollama_troubleshooting_html

    return ollama_troubleshooting_html(error)
