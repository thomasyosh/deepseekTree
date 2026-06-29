"""Build a standalone HTML file from a chat session for download."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any

from chat_normalize import is_export_request


def _qa_pairs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair each user question with the following assistant answer."""
    pairs: list[dict[str, Any]] = []
    pending_question: str | None = None

    for msg in messages:
        role = msg.get("role", "")
        text = (msg.get("text") or "").strip()
        if not text:
            continue

        if role == "user":
            if is_export_request(text):
                continue
            pending_question = text
        elif role == "assistant" and pending_question:
            pairs.append(
                {
                    "question": pending_question,
                    "answer": text,
                    "is_html": bool(msg.get("isHtml") or msg.get("is_html")),
                }
            )
            pending_question = None

    return pairs


def _strip_outer_section(fragment: str) -> str:
    """Use inner HTML when answers already wrap query-result sections."""
    match = re.search(
        r'<section[^>]*class="query-result"[^>]*>(.*)</section>',
        fragment,
        re.DOTALL | re.IGNORECASE,
    )
    return match.group(1).strip() if match else fragment


def _qa_section(index: int, pair: dict[str, Any]) -> str:
    question = html.escape(pair["question"])
    answer_raw = pair["answer"]
    if pair.get("is_html"):
        answer_body = _strip_outer_section(answer_raw)
    else:
        answer_body = f"<p>{html.escape(answer_raw)}</p>"

    return f"""
    <section class="qa-card">
      <p class="qa-num">Question {index}</p>
      <h2 class="qa-question">{question}</h2>
      <h3>Answer</h3>
      <div class="qa-answer">{answer_body}</div>
    </section>
    """


def build_chat_export_html(
    messages: list[dict[str, Any]],
    summary: dict[str, Any],
    *,
    title: str | None = None,
) -> str:
    """Render a self-contained HTML report focused on the user's questions."""
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pairs = _qa_pairs(messages)
    doc_title = html.escape(title or "Tree Complaint Analysis — Chat Report")

    dr = summary.get("date_range", ["—", "—"])
    context = f"""
    <section class="card context">
      <h2>Report context</h2>
      <ul>
        <li><strong>Questions answered:</strong> {len(pairs)}</li>
        <li><strong>Dataset size:</strong> {summary.get("total_cases", 0)} cases</li>
        <li><strong>Data date range:</strong> {html.escape(str(dr[0]))} → {html.escape(str(dr[1]))}</li>
        <li><strong>Generated:</strong> {generated}</li>
      </ul>
    </section>
    """

    if pairs:
        body = "".join(_qa_section(i, pair) for i, pair in enumerate(pairs, 1))
        intro = (
            "<p>This report contains the questions you asked in the chat "
            "and the answers returned by the analyst.</p>"
        )
    else:
        body = (
            '<section class="card"><p class="empty">'
            "No question-and-answer pairs to export. "
            "Ask questions in the chat, then download again."
            "</p></section>"
        )
        intro = ""

    return f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{doc_title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      margin: 0;
      background: #f4f6f8;
      color: #1a1a2e;
      line-height: 1.55;
    }}
    .wrap {{ max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem; }}
    h1 {{ margin-top: 0; font-size: 1.75rem; }}
    .card, .qa-card {{
      background: #fff;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      padding: 1.25rem 1.5rem;
      margin-bottom: 1.25rem;
    }}
    .qa-num {{
      margin: 0 0 0.35rem;
      font-size: 0.8rem;
      font-weight: 600;
      color: #2563eb;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .qa-question {{
      margin: 0 0 1rem;
      font-size: 1.15rem;
      line-height: 1.4;
    }}
    .qa-card h3 {{
      margin: 0 0 0.5rem;
      font-size: 0.95rem;
      color: #5c6370;
    }}
    .qa-answer {{ overflow-x: auto; }}
    .qa-answer table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 0.5rem;
    }}
    .qa-answer th, .qa-answer td {{
      text-align: left;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid #e5e7eb;
    }}
    .context ul {{ margin: 0; padding-left: 1.25rem; }}
    .footer {{
      font-size: 0.85rem;
      color: #5c6370;
      margin-top: 2rem;
    }}
    @media print {{
      body {{ background: #fff; }}
      .qa-card, .card {{ break-inside: avoid; page-break-inside: avoid; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{doc_title}</h1>
    {intro}
    {context}
    {body}
    <p class="footer">Generated by Tree Complaint Analyst · {generated}</p>
  </div>
</body>
</html>
"""
