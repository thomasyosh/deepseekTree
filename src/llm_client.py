"""Local DeepSeek via Ollama using requests with proxy bypass."""
from __future__ import annotations

import time
from typing import Any

import requests

import config
import filelogger


def _request_timeout(read_timeout: int | None) -> tuple[int, int]:
    return (config.CHAT_CONNECT_TIMEOUT, read_timeout or config.CHAT_TIMEOUT)


def _ollama_post(url: str, payload: dict[str, Any], read_timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    response = requests.post(
        url,
        json=payload,
        proxies=config.NO_PROXY,
        timeout=_request_timeout(read_timeout),
    )
    elapsed = time.monotonic() - started
    filelogger.logger.info(
        f"Ollama responded in {elapsed:.1f}s status={response.status_code} url={url}"
    )
    response.raise_for_status()
    return response.json()


def _extract_chat_content(data: dict[str, Any], *, require_content: bool) -> str:
    message = data.get("message") or {}
    content = (message.get("content") or "").strip()
    if content:
        return content

    thinking = (message.get("thinking") or "").strip()
    if data.get("done") and not require_content:
        return content or thinking or "OK"

    if thinking and data.get("done_reason") == "length":
        raise RuntimeError(
            "DeepSeek used all tokens on internal reasoning before producing a reply. "
            "Increase CHAT_MAX_TOKENS (try 512) or use a smaller prompt."
        )

    if require_content:
        raise RuntimeError(f"Unexpected Ollama response (empty content): {data}")
    return content


def chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    stream: bool = False,
    timeout: int | None = None,
    max_tokens: int = 1500,
    require_content: bool = True,
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
        f"Calling Ollama model={model_name} prompt_chars={prompt_chars} "
        f"max_tokens={max_tokens} read_timeout={read_timeout}s"
    )

    data = _ollama_post(url, payload, read_timeout)
    return _extract_chat_content(data, require_content=require_content)


def warm_up_model(timeout: int | None = None) -> bool:
    """Load the model into memory. Never raises — startup must not fail here."""
    if not config.OLLAMA_WARMUP:
        filelogger.logger.info("Ollama warm-up skipped (OLLAMA_WARMUP=false)")
        return True

    read_timeout = timeout or config.OLLAMA_TIMEOUT
    model_name = config.CHAT_MODEL
    url = f"{config.OLLAMA_BASE_URL}/api/generate"

    try:
        filelogger.logger.info(
            f"Warming up Ollama model={model_name} via /api/generate "
            f"(timeout={read_timeout}s)..."
        )
        data = _ollama_post(
            url,
            {
                "model": model_name,
                "prompt": "Hello",
                "stream": False,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
            },
            read_timeout,
        )
        if data.get("done"):
            filelogger.logger.info("Ollama warm-up complete (model loaded)")
            return True
        filelogger.logger.warning(f"Ollama warm-up returned unexpected payload: {data}")
        return False
    except Exception as e:
        filelogger.logger.warning(f"Ollama warm-up failed (server will still start): {e}")
        return False


def get_runtime_model_info() -> dict[str, Any]:
    """Configured model settings plus live Ollama metadata when reachable."""
    health = check_llm_health()
    model_name = config.CHAT_MODEL
    info: dict[str, Any] = {
        "provider": config.LLM_PROVIDER,
        "chat_model": config.CHAT_MODEL,
        "report_model": config.REPORT_MODEL,
        "ollama_base_url": config.OLLAMA_BASE_URL,
        "chat_timeout_seconds": config.CHAT_TIMEOUT,
        "chat_max_tokens": config.CHAT_MAX_TOKENS,
        "ollama_ok": health.get("ok", False),
        "models_available": health.get("models_available", []),
        "model_modified_at": None,
        "model_size_bytes": None,
        "health_error": health.get("error"),
        "health_hints": health.get("hints", []),
    }

    if not health.get("ok"):
        return info

    try:
        response = requests.get(
            f"{config.OLLAMA_BASE_URL}/api/tags",
            proxies=config.NO_PROXY,
            timeout=(config.CHAT_CONNECT_TIMEOUT, 10),
        )
        response.raise_for_status()
        for entry in response.json().get("models", []):
            name = entry.get("name", "")
            if name == model_name or name.startswith(f"{model_name}:"):
                info["model_modified_at"] = entry.get("modified_at")
                info["model_size_bytes"] = entry.get("size")
                info["resolved_model_name"] = name
                break
    except requests.exceptions.RequestException as e:
        info["health_error"] = str(e)

    return info


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
        if config.CHAT_MAX_TOKENS < 256:
            health["hints"].append(
                "DeepSeek-R1 may need CHAT_MAX_TOKENS=512 (reasoning uses tokens before the reply)"
            )
    except requests.exceptions.RequestException as e:
        health["error"] = str(e)
        health["hints"] = [
            "Install and start Ollama from https://ollama.com",
            f"Set OLLAMA_BASE_URL={config.OLLAMA_BASE_URL} in .env",
            f"Increase CHAT_TIMEOUT (current: {config.CHAT_TIMEOUT}s)",
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
    extra = (
        f"<li>Increase <code>CHAT_MAX_TOKENS</code> (current: {config.CHAT_MAX_TOKENS}) "
        "— DeepSeek-R1 uses tokens for reasoning first.</li>"
        f"<li>Increase <code>CHAT_TIMEOUT</code> (current: {config.CHAT_TIMEOUT}s).</li>"
    )
    return html.replace("</ol>", extra + "</ol>", 1)
