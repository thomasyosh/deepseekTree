"""Local DeepSeek via Ollama using requests with proxy bypass."""
from __future__ import annotations

import time
from typing import Any

import requests

import config
import filelogger


def _request_timeout(read_timeout: int | None) -> tuple[int, int]:
    return (config.CHAT_CONNECT_TIMEOUT, read_timeout or config.CHAT_TIMEOUT)


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
    read_timeout = timeout or config.CHAT_TIMEOUT
    url = f"{config.OLLAMA_BASE_URL}/api/chat"
    payload: dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "keep_alive": config.OLLAMA_KEEP_ALIVE,
        "think": False,
        "options": {
            "num_predict": max_tokens,
            "num_ctx": config.OLLAMA_NUM_CTX,
        },
    }

    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    filelogger.logger.info(
        f"Calling Ollama model={model_name} url={url} "
        f"prompt_chars={prompt_chars} read_timeout={read_timeout}s think=false"
    )

    started = time.monotonic()
    response = requests.post(
        url,
        json=payload,
        proxies=config.NO_PROXY,
        timeout=_request_timeout(read_timeout),
    )
    elapsed = time.monotonic() - started
    filelogger.logger.info(f"Ollama responded in {elapsed:.1f}s status={response.status_code}")

    response.raise_for_status()
    data = response.json()
    message = data.get("message", {})
    content = message.get("content")
    if not content:
        raise RuntimeError(f"Unexpected Ollama response: {data}")
    return content


def warm_up_model(timeout: int | None = None) -> bool:
    """Load the model into memory before the first user chat (avoids first-request timeout)."""
    read_timeout = timeout or config.OLLAMA_TIMEOUT
    try:
        filelogger.logger.info(
            f"Warming up Ollama model={config.CHAT_MODEL} (timeout={read_timeout}s)..."
        )
        chat_completion(
            [{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=8,
            timeout=read_timeout,
        )
        filelogger.logger.info("Ollama warm-up complete")
        return True
    except requests.exceptions.RequestException as e:
        filelogger.logger.warning(f"Ollama warm-up failed: {e}")
        return False


def check_llm_health(timeout: int = 5) -> dict[str, Any]:
    health: dict[str, Any] = {
        "ok": False,
        "provider": "ollama",
        "base_url": config.OLLAMA_BASE_URL,
        "model_configured": config.CHAT_MODEL,
        "chat_timeout_seconds": config.CHAT_TIMEOUT,
        "models_available": [],
        "error": None,
        "hints": [],
        "proxy_bypass": config.NO_PROXY,
    }

    try:
        response = requests.get(
            f"{config.OLLAMA_BASE_URL}/api/tags",
            proxies=config.NO_PROXY,
            timeout=(config.CHAT_CONNECT_TIMEOUT, timeout),
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
        if config.CHAT_TIMEOUT < 180:
            health["hints"].append(
                f"CHAT_TIMEOUT={config.CHAT_TIMEOUT}s may be too low for CPU inference; use 300+"
            )
    except requests.exceptions.RequestException as e:
        health["error"] = str(e)
        health["hints"] = [
            "Install and start Ollama from https://ollama.com",
            f"Set OLLAMA_BASE_URL={config.OLLAMA_BASE_URL} in .env",
            f"Increase CHAT_TIMEOUT (current: {config.CHAT_TIMEOUT}s) — CPU models need 300s+",
            "Use deepseek-r1:7b instead of 14b on company laptops",
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

    html = ollama_troubleshooting_html(error)
    return html.replace(
        "</ol>",
        f"<li>Increase <code>CHAT_TIMEOUT</code> (current: {config.CHAT_TIMEOUT}s). "
        "Try <code>300</code> or <code>600</code> for CPU inference.</li></ol>",
        1,
    )
