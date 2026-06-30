import http.client
import json
import os
import socket
from pathlib import Path
from typing import Any

import requests

import config
import filelogger
import llm_client
from prompts import (
    CHAT_SYSTEM_PROMPT,
    REPORT_SYSTEM_PROMPT,
    build_chat_user_prompt,
    build_open_chat_user_prompt,
    build_unified_chat_user_prompt,
)
from chat_normalize import is_dataset_data_question, normalize_user_message
from query_engine import build_llm_prompt, date_facts, detect_intent
from report_builder import build_report_html
from summary import build_summary


def _ollama_post_json(payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Call Ollama over a raw TCP socket (never goes through HTTP proxy)."""
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPConnection(
        config.OLLAMA_HOST, config.OLLAMA_PORT, timeout=timeout
    )
    try:
        conn.request(
            "POST",
            config.OLLAMA_PATH,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        if resp.status >= 400:
            fake_response = type(
                "Resp",
                (),
                {"status_code": resp.status, "text": text, "reason": resp.reason},
            )()
            raise requests.exceptions.HTTPError(
                f"{resp.status} Client Error: {resp.reason} for url {config.OLLAMA_URL}",
                response=fake_response,
            )
        return json.loads(text)
    except (TimeoutError, socket.timeout) as e:
        raise requests.exceptions.Timeout(str(e)) from e
    except OSError as e:
        raise requests.exceptions.ConnectionError(str(e)) from e
    finally:
        conn.close()


def _is_proxy_policy_page(body: str) -> bool:
    lower = body.lower().strip()
    return lower.startswith("<!doctype") or lower.startswith("<html") or (
        "<body" in lower and "policy" in lower
    )


def _proxy_bypass_hints() -> list[str]:
    return [
        "Your company proxy intercepts http://localhost — curl may show a policy HTML "
        "page even when Ollama is fine. That is NOT a valid Ollama test.",
        "Test Ollama without the proxy: "
        "curl.exe --noproxy \"*\" http://127.0.0.1:11434/api/tags",
        "Always use 127.0.0.1 (not localhost) in .env: "
        "OLLAMA_URL=http://127.0.0.1:11434/v1/chat/completions",
        "Windows proxy bypass: Settings → Network → Proxy → "
        "\"Bypass proxy server for these addresses\" add: "
        "localhost;127.0.0.1;<local>",
        "Or before starting the server: "
        'set NO_PROXY=localhost,127.0.0.1,<local>',
        "This app's Ollama calls use a direct TCP socket to 127.0.0.1 (not the proxy). "
        "Open http://127.0.0.1:8000/api/ollama-health for the real status.",
    ]


def check_ollama_health(timeout: int = 5) -> dict[str, Any]:
    """Probe Ollama /api/tags and return diagnostics for colleagues."""
    health: dict[str, Any] = {
        "ok": False,
        "url": config.OLLAMA_URL,
        "host": config.OLLAMA_HOST,
        "port": config.OLLAMA_PORT,
        "model_configured": config.CHAT_MODEL,
        "models_available": [],
        "error": None,
        "hints": [],
        "proxy_env": {
            "HTTP_PROXY": os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"),
            "HTTPS_PROXY": os.environ.get("HTTPS_PROXY")
            or os.environ.get("https_proxy"),
            "NO_PROXY": os.environ.get("NO_PROXY") or os.environ.get("no_proxy"),
        },
    }

    if config.OLLAMA_HOST == "ollama":
        health["hints"].append(
            "OLLAMA_URL uses hostname 'ollama' — that only works inside Docker. "
            "For native Python set OLLAMA_URL=http://127.0.0.1:11434/v1/chat/completions "
            "in .env and restart the server."
        )

    conn = http.client.HTTPConnection(
        config.OLLAMA_HOST, config.OLLAMA_PORT, timeout=timeout
    )
    try:
        conn.request("GET", "/api/tags")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8", errors="replace")
        if resp.status != 200:
            health["error"] = f"HTTP {resp.status}: {body[:300]}"
            if _is_proxy_policy_page(body):
                health["hints"].extend(_proxy_bypass_hints())
            else:
                health["hints"].append(
                    "Ollama responded but with an error. Check the Ollama app logs."
                )
            return health

        if _is_proxy_policy_page(body):
            health["error"] = "Received company proxy policy HTML instead of Ollama JSON"
            health["hints"].extend(_proxy_bypass_hints())
            return health

        data = json.loads(body)
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        health["models_available"] = models
        health["ok"] = True

        if not _model_is_available(config.CHAT_MODEL, models):
            health["hints"].append(
                f"Model '{config.CHAT_MODEL}' is not installed. "
                f"Run in a terminal: ollama pull {config.CHAT_MODEL}"
            )
        return health
    except ConnectionRefusedError:
        health["error"] = (
            f"Connection refused to {config.OLLAMA_HOST}:{config.OLLAMA_PORT}"
        )
        health["hints"].extend(_ollama_not_running_hints())
        return health
    except OSError as e:
        health["error"] = str(e)
        if "10061" in str(e) or "refused" in str(e).lower():
            health["hints"].extend(_ollama_not_running_hints())
        else:
            health["hints"].append(
                f"Cannot open TCP to {config.OLLAMA_HOST}:{config.OLLAMA_PORT}. "
                "Check firewall or OLLAMA_URL in .env."
            )
        return health
    except (TimeoutError, socket.timeout) as e:
        health["error"] = f"Timed out after {timeout}s: {e}"
        health["hints"].append("Ollama is not responding. Is the Ollama app running?")
        return health
    except json.JSONDecodeError as e:
        health["error"] = f"Invalid JSON from Ollama: {e}"
        health["hints"].extend(_proxy_bypass_hints())
        return health
    finally:
        conn.close()


def _model_is_available(model: str, available: list[str]) -> bool:
    if not available:
        return False
    if model in available:
        return True
    prefix = f"{model}:"
    return any(name == model or name.startswith(prefix) for name in available)


def _ollama_not_running_hints() -> list[str]:
    return [
        "Install Ollama from https://ollama.com if you have not already.",
        "Start the Ollama desktop app (or run: ollama serve).",
        "In .env set: OLLAMA_URL=http://127.0.0.1:11434/v1/chat/completions",
        "Do NOT test with: curl http://localhost:11434 (proxy may return policy HTML).",
        "Test without proxy: curl.exe --noproxy \"*\" http://127.0.0.1:11434/api/tags",
        "Then pull the model: ollama pull deepseek-r1:7b",
        "Restart uvicorn after changing .env.",
    ]


def ollama_troubleshooting_html(error: Exception | None = None) -> str:
    health = check_ollama_health(timeout=3)
    lines = [
        "<p><strong>Could not reach Ollama.</strong></p>",
        f"<p>Configured URL: <code>{health['url']}</code></p>",
    ]
    if health["error"]:
        lines.append(f"<p><em>{health['error']}</em></p>")
    if error and str(error) != health.get("error"):
        lines.append(f"<p><em>{error}</em></p>")
    if health["hints"]:
        lines.append("<p><strong>Checklist:</strong></p><ol>")
        for hint in health["hints"]:
            lines.append(f"<li>{hint}</li>")
        lines.append("</ol>")
    else:
        lines.extend(_ollama_not_running_hints_html())
    lines.append(
        "<p>Run diagnostics: <a href='/api/ollama-health'>GET /api/ollama-health</a></p>"
    )
    return "".join(lines)


def _ollama_not_running_hints_html() -> list[str]:
    return [
        "<p><strong>Checklist:</strong></p><ol>",
        *[f"<li>{h}</li>" for h in _ollama_not_running_hints()],
        "</ol>",
    ]


def _ollama_chat_completion(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    stream: bool = False,
    timeout: int | None = None,
    max_tokens: int = 1500,
) -> str:
    model_name = model or config.AI_MODEL
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": stream,
        "options": {
            "num_predict": max_tokens,
            "num_ctx": config.OLLAMA_NUM_CTX,
        },
    }

    request_timeout = timeout or config.OLLAMA_TIMEOUT
    filelogger.logger.info(
        f"Calling Ollama model={model_name} "
        f"host={config.OLLAMA_HOST}:{config.OLLAMA_PORT}{config.OLLAMA_PATH} "
        f"(direct TCP, no proxy)"
    )
    data = _ollama_post_json(payload, request_timeout)
    if "choices" not in data:
        raise RuntimeError(f"Unexpected Ollama response: {data}")

    return data["choices"][0]["message"]["content"]


def build_analysis_messages(summary: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Produce the full analysis report section from this summary:\n\n"
                f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_chat_messages(
    summary: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    normalized = normalize_user_message(user_message)
    query_text = normalized or user_message.strip()

    if config.CHAT_FORCE_AI:
        data: dict[str, Any] = {
            "summary": summary,
            "date_facts": date_facts(rows) if rows else {},
        }
        user_content = build_unified_chat_user_prompt(
            user_message,
            data,
            normalized_message=query_text if query_text != user_message.strip() else None,
        )
    elif is_dataset_data_question(user_message):
        if rows:
            llm_prompt = build_llm_prompt(user_message, rows, summary)
            if llm_prompt:
                user_content = llm_prompt[0]
            else:
                user_content = build_chat_user_prompt(
                    user_message,
                    detect_intent(query_text, rows).value,
                    {"summary": summary, "date_facts": date_facts(rows)},
                    normalized_message=query_text if query_text != user_message.strip() else None,
                )
        else:
            user_content = build_chat_user_prompt(
                user_message,
                detect_intent(query_text).value,
                {"summary": summary},
                normalized_message=query_text if query_text != user_message.strip() else None,
            )
    else:
        user_content = build_open_chat_user_prompt(
            user_message,
            normalized_message=query_text if query_text != user_message.strip() else None,
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
    ]
    messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_content})
    return messages


def analyze(
    data_path: Path | None = None,
    report_path: Path | None = None,
    *,
    use_llm: bool = True,
) -> Path:
    data_path = data_path or config.DATA_PATH
    report_path = report_path or config.REPORT_PATH

    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    rows = json.loads(data_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("data.json must contain a JSON array of records")

    summary = build_summary(rows)
    filelogger.logger.info(
        f"Built summary for {summary['total_cases']} cases "
        f"({len(json.dumps(summary, ensure_ascii=False))} chars)"
    )

    narrative = (
        "<p><em>Summary refreshed from latest data. "
        "Use POST /api/refresh for full AI narrative.</em></p>"
    )
    if use_llm:
        try:
            narrative = llm_client.chat_completion(
                build_analysis_messages(summary),
                model=config.REPORT_MODEL,
                max_tokens=1200,
                timeout=config.OLLAMA_TIMEOUT,
            )
        except requests.exceptions.RequestException as e:
            filelogger.logger.error(f"LLM analysis failed: {e}")
            narrative = (
                "<p><em>AI analysis unavailable. Review the summary tables above.</em></p>"
            )
    html = build_report_html(summary, narrative, rows=rows)
    report_path.write_text(html, encoding="utf-8")
    filelogger.logger.info(f"Report written to {report_path}")
    return report_path
