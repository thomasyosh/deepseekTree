import http.client
import json
import socket
from pathlib import Path
from typing import Any

import requests

import config
import filelogger
from prompts import CHAT_SYSTEM_PROMPT, REPORT_SYSTEM_PROMPT, build_chat_user_prompt
from query_engine import build_llm_prompt, detect_intent, execute_query
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

def chat_completion(
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
        "options": {"num_predict": max_tokens},
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
    if rows:
        llm_prompt = build_llm_prompt(user_message, rows, summary)
        user_content = llm_prompt[0] if llm_prompt else user_message
    else:
        intent = detect_intent(user_message).value
        user_content = build_chat_user_prompt(
            user_message, intent, {"summary": summary}
        )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
    ]
    messages.extend(history[-4:])
    messages.append({"role": "user", "content": user_content})
    return messages


def analyze(data_path: Path | None = None, report_path: Path | None = None) -> Path:
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
        "<p><em>AI analysis unavailable. Review the summary tables above.</em></p>"
    )
    try:
        narrative = chat_completion(
            build_analysis_messages(summary),
            model=config.REPORT_MODEL,
            max_tokens=1200,
            timeout=config.OLLAMA_TIMEOUT,
        )
    except requests.exceptions.RequestException as e:
        filelogger.logger.error(f"Ollama analysis failed: {e}")
    html = build_report_html(summary, narrative)
    report_path.write_text(html, encoding="utf-8")
    filelogger.logger.info(f"Report written to {report_path}")
    return report_path
