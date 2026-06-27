import json
from pathlib import Path
from typing import Any

import requests

import config
import filelogger
from report_builder import build_report_html
from summary import build_summary


def chat_completion(
    messages: list[dict[str, str]],
    *,
    stream: bool = False,
    timeout: int | None = None,
    max_tokens: int = 1500,
) -> str:
    payload = {
        "model": config.AI_MODEL,
        "messages": messages,
        "stream": stream,
        "options": {"num_predict": max_tokens},
    }

    request_timeout = timeout or config.OLLAMA_TIMEOUT
    filelogger.logger.info(f"Calling Ollama model={config.AI_MODEL}")
    response = requests.post(
        config.OLLAMA_URL, json=payload, timeout=request_timeout
    )
    response.raise_for_status()
    data = response.json()

    if "choices" not in data:
        raise RuntimeError(f"Unexpected Ollama response: {data}")

    return data["choices"][0]["message"]["content"]


def build_analysis_messages(summary: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are a data analyst for Hong Kong tree complaint cases. "
                "Write clear, concise analysis using HTML tags (<p>, <ul>, <li>, <strong>). "
                "Do not include <html>, <head>, or <body> wrappers."
            ),
        },
        {
            "role": "user",
            "content": (
                "Analyze this pre-aggregated dataset summary and produce an HTML report section "
                "with: executive summary, key trends, district hotspots, severity insights, "
                "and actionable recommendations.\n\n"
                f"{json.dumps(summary, ensure_ascii=False, indent=2)}"
            ),
        },
    ]


def build_chat_messages(
    summary: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    sample_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    context = {
        "summary": summary,
        "sample_rows": sample_rows or [],
    }
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are a helpful data analyst assistant for tree complaint cases in Hong Kong. "
                "Answer using the provided summary statistics and sample rows. "
                "Be concise and cite numbers from the summary when possible.\n\n"
                f"{json.dumps(context, ensure_ascii=False, indent=2)}"
            ),
        },
    ]
    messages.extend(history[-10:])
    messages.append({"role": "user", "content": user_message})
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
            max_tokens=1200,
            timeout=180,
        )
    except requests.exceptions.RequestException as e:
        filelogger.logger.error(f"Ollama analysis failed: {e}")
    html = build_report_html(summary, narrative)
    report_path.write_text(html, encoding="utf-8")
    filelogger.logger.info(f"Report written to {report_path}")
    return report_path
