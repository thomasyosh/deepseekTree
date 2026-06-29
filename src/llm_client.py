"""LLM client using the OpenAI Python SDK.

Default: local DeepSeek via Ollama's OpenAI-compatible API (/v1/chat/completions).
Optional: set LLM_PROVIDER=cloud for OpenAI's hosted API.
"""
from __future__ import annotations

from typing import Any

import httpx
from openai import OpenAI

import config
import filelogger

_client: OpenAI | None = None


def _is_local_ollama() -> bool:
    return config.LLM_PROVIDER != "cloud"


def _client_instance() -> OpenAI:
    global _client
    if _client is not None:
        return _client

    if _is_local_ollama():
        # Ollama exposes an OpenAI-compatible API; api_key is required but ignored.
        http_client = httpx.Client(
            proxy=None,
            timeout=config.OLLAMA_TIMEOUT,
        )
        _client = OpenAI(
            base_url=config.OLLAMA_OPENAI_BASE_URL,
            api_key=config.OLLAMA_API_KEY,
            http_client=http_client,
        )
        return _client

    if not config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=cloud")

    http_client = httpx.Client(
        proxy=config.PROXY or None,
        verify=config.VERIFY_SSL,
        timeout=config.OLLAMA_TIMEOUT,
    )
    kwargs: dict[str, Any] = {
        "api_key": config.OPENAI_API_KEY,
        "http_client": http_client,
    }
    if config.OPENAI_BASE_URL:
        kwargs["base_url"] = config.OPENAI_BASE_URL
    _client = OpenAI(**kwargs)
    return _client


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
    request_timeout = float(timeout or config.CHAT_TIMEOUT)
    backend = (
        f"local Ollama @ {config.OLLAMA_OPENAI_BASE_URL}"
        if _is_local_ollama()
        else "OpenAI cloud"
    )
    filelogger.logger.info(
        f"Calling model={model_name} via OpenAI SDK ({backend})"
    )

    client = _client_instance()
    extra_body: dict[str, Any] | None = None
    if _is_local_ollama():
        extra_body = {
            "options": {
                "num_predict": max_tokens,
                "num_ctx": config.OLLAMA_NUM_CTX,
            }
        }

    response = client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=max_tokens,
        timeout=request_timeout,
        extra_body=extra_body,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"Empty LLM response: {response}")
    return content


def check_llm_health(timeout: int = 5) -> dict[str, Any]:
    if _is_local_ollama():
        return _check_local_ollama_health(timeout)
    return _check_cloud_health(timeout)


def _check_local_ollama_health(timeout: int = 5) -> dict[str, Any]:
    from deepseek import check_ollama_health

    health = check_ollama_health(timeout)
    health["provider"] = "ollama"
    health["api_format"] = "openai-compatible"
    health["base_url"] = config.OLLAMA_OPENAI_BASE_URL
    return health


def _check_cloud_health(timeout: int = 5) -> dict[str, Any]:
    health: dict[str, Any] = {
        "ok": False,
        "provider": "cloud",
        "api_format": "openai",
        "model_configured": config.CHAT_MODEL,
        "error": None,
        "hints": [],
    }
    if not config.OPENAI_API_KEY:
        health["error"] = "OPENAI_API_KEY is not set"
        health["hints"] = ["Set OPENAI_API_KEY or use LLM_PROVIDER=ollama for local DeepSeek"]
        return health
    try:
        _client_instance().models.list(timeout=float(timeout))
        health["ok"] = True
    except Exception as e:
        health["error"] = str(e)
    return health


def llm_troubleshooting_html(error: Exception | None = None) -> str:
    from deepseek import ollama_troubleshooting_html

    if _is_local_ollama():
        html = ollama_troubleshooting_html(error)
        return html.replace(
            "Could not reach Ollama.",
            "Could not reach local DeepSeek (Ollama OpenAI API).",
        )

    health = _check_cloud_health(timeout=3)
    lines = [
        "<p><strong>Could not reach OpenAI cloud API.</strong></p>",
        f"<p><em>{health.get('error') or error}</em></p>",
        "<p>For local DeepSeek, set <code>LLM_PROVIDER=ollama</code> in .env.</p>",
    ]
    return "".join(lines)
