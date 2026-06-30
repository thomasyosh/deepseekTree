"""Standardized prompts for consistent HTML output."""

import html
import json
from typing import Any

# Allowed HTML tags the model may use (enforced in system prompt).
ALLOWED_TAGS = "section, h3, p, table, thead, tbody, tr, th, td, ol, li, strong, em"

CHAT_EXAMPLE_QUESTIONS: list[str] = [
    "What is the earliest case date?",
    "Top 5 districts by severe cases",
    "How many cases in 沙田?",
    "Show 5 newest cases",
    "Overview of the dataset",
]

CHAT_SYSTEM_PROMPT = f"""You are a helpful assistant in a Hong Kong tree complaint analysis app.
Users may ask **any** question — general knowledge or data analysis.

HOW TO ANSWER:
1. **General questions** (today's date, time, definitions, weather, small talk, opinions):
   Answer directly from general knowledge. Be concise and accurate.
2. **Tree-complaint data questions** (districts, cases, severity, dates in the dataset):
   Use ONLY the pre-computed data in the user message. Never invent case counts or statistics.
3. If a question mixes both, answer the general part and the data part clearly.

DATA RULES (when dataset is provided):
- case_date: actual complaint date per row (YYYY-MM-DD).
- summary.date_range is [min, max] only — for earliest/latest case cite case_no and case_date from rows.
- Accept English, 繁體中文, and 简体中文; correct obvious typos mentally.

OUTPUT RULES (strict):
1. Reply with HTML only — no markdown, no ``` fences, no <html>/<body>.
2. Use only these tags: {ALLOWED_TAGS}.
3. Always wrap output in: <section class="query-result">...</section>
4. Start with <h3>Title</h3> describing what the result shows.
5. Use <table> for row-level case data; use <ol> for ranked lists.
6. Keep responses concise unless the user asks for detail.
7. Respond immediately — no chain-of-thought, no reasoning blocks."""

REPORT_SYSTEM_PROMPT = f"""You are a data analyst for Hong Kong tree complaint cases.

OUTPUT RULES (strict):
1. Write HTML only — no markdown, no ``` fences, no <html>/<head>/<body>.
2. Use only: p, h3, ul, li, strong, em, table, thead, tbody, tr, th, td.
3. Structure: executive summary, key trends, district hotspots, severity insights, recommendations.
4. Use only statistics from the provided summary — never invent numbers."""


INTENT_HTML_SCHEMA: dict[str, str] = {
    "rank": """
<section class="query-result">
  <h3>Top N [category] by [metric]</h3>
  <ol>
    <li><strong>Name</strong>: count cases</li>
  </ol>
</section>""".strip(),
    "sort_cases": """
<section class="query-result">
  <h3>N newest/oldest cases</h3>
  <table>
    <thead><tr><th>#</th><th>Case No</th><th>Date</th><th>District</th><th>Severity</th><th>Status</th></tr></thead>
    <tbody>
      <tr><td>1</td><td>TC2026001</td><td>2026-06-20</td><td>沙田</td><td>嚴重</td><td>新個案</td></tr>
    </tbody>
  </table>
</section>""".strip(),
    "filter": """
<section class="query-result">
  <h3>Filtered results</h3>
  <p>Showing <strong>N</strong> matching cases.</p>
  <table>...</table>
</section>""".strip(),
    "overview": """
<section class="query-result">
  <h3>Dataset Overview</h3>
  <ul>
    <li><strong>Total cases:</strong> N</li>
  </ul>
</section>""".strip(),
    "date_extreme": """
<section class="query-result">
  <h3>Earliest / latest case by case_date</h3>
  <p>The <strong>earliest</strong> case date is <strong>YYYY-MM-DD</strong> (case_no: TC...).</p>
  <table>
    <thead><tr><th>#</th><th>Case No</th><th>Date</th><th>District</th><th>Severity</th><th>Status</th></tr></thead>
    <tbody>...</tbody>
  </table>
</section>""".strip(),
    "generic": """
<section class="query-result">
  <h3>Answer</h3>
  <p>Concise answer using the pre-computed data.</p>
</section>""".strip(),
    "clarification": """
<section class="query-result">
  <h3>How to ask</h3>
  <p>Brief note if the question was unclear or off-topic.</p>
  <p>Try one of these:</p>
  <ol>
    <li>Example question 1</li>
  </ol>
</section>""".strip(),
}


def build_chat_welcome_html() -> str:
    items = "".join(f"<li><code>{html.escape(q)}</code></li>" for q in CHAT_EXAMPLE_QUESTIONS)
    return (
        '<section class="query-result"><h3>Tree complaint analyst</h3>'
        "<p>You can ask <strong>any question</strong> — general topics (e.g. today's date) "
        "or tree-complaint data (districts, severity, case counts). "
        "Typos are OK.</p>"
        "<p>When finished, type <code>download report</code> or click "
        "<strong>Download chat report</strong> to save your Q&amp;A as HTML.</p>"
        f"<p><strong>Data examples:</strong></p><ol>{items}</ol></section>"
    )


def build_clarification_html(reason: str) -> str:
    items = "".join(f"<li><code>{html.escape(q)}</code></li>" for q in CHAT_EXAMPLE_QUESTIONS)
    return (
        '<section class="query-result"><h3>Need a bit more detail</h3>'
        f"<p>{html.escape(reason)}</p>"
        f"<p><strong>Try asking:</strong></p><ol>{items}</ol></section>"
    )


def build_scope_redirect_html() -> str:
    return build_clarification_html(
        "I can only answer questions about the tree complaint dataset shown in this report."
    )


def build_export_ready_html() -> str:
    return (
        '<section class="query-result"><h3>Downloading your report</h3>'
        "<p>Building an HTML file from <strong>your questions and answers</strong> "
        "in this chat session.</p>"
        "<p>If the download does not start, click <strong>Download chat report</strong> "
        "below the chat box.</p></section>"
    )


def build_export_need_questions_html() -> str:
    return build_clarification_html(
        "Ask at least one question about the data first, then type "
        '"download report" or click Download chat report.'
    )


def build_system_meta_html(info: dict[str, Any], question: str) -> str:
    """Answer questions about the analyst / LLM configuration (not case data)."""
    lower = question.lower()
    wants_update = any(
        phrase in lower
        for phrase in ("last updated", "last modified", "modified", "updated", "when was")
    )
    wants_running = any(
        phrase in lower for phrase in ("running", "currently", "configured", "which model", "what model")
    )

    model = html.escape(str(info.get("chat_model", "—")))
    provider = html.escape(str(info.get("provider", "—")))
    base_url = html.escape(str(info.get("ollama_base_url", "—")))
    resolved = info.get("resolved_model_name")
    resolved_html = (
        f'<li><strong>Ollama model tag:</strong> {html.escape(resolved)}</li>'
        if resolved and resolved != info.get("chat_model")
        else ""
    )

    status = "Connected" if info.get("ollama_ok") else "Not reachable"
    if info.get("ollama_ok") is None:
        status = "Configured (.env) — live status not checked"
    status_detail = ""
    if info.get("health_error"):
        status_detail = f"<p><em>{html.escape(str(info['health_error']))}</em></p>"

    modified = info.get("model_modified_at")
    modified_line = ""
    if modified:
        modified_line = (
            f"<li><strong>Model last modified (Ollama):</strong> "
            f"{html.escape(str(modified))}</li>"
        )
    elif wants_update:
        modified_line = (
            "<li><strong>Model last modified:</strong> "
            "Unavailable — Ollama did not return metadata for this model.</li>"
        )

    size = info.get("model_size_bytes")
    size_line = ""
    if size:
        size_gb = int(size) / (1024**3)
        size_line = f"<li><strong>Model size on disk:</strong> {size_gb:.2f} GB</li>"

    available = info.get("models_available") or []
    available_line = ""
    if available:
        items = "".join(f"<li><code>{html.escape(name)}</code></li>" for name in available[:8])
        extra = f"<li><em>…and {len(available) - 8} more</em></li>" if len(available) > 8 else ""
        available_line = f"<h3>Models installed in Ollama</h3><ol>{items}{extra}</ol>"

    title = "AI model information"
    if wants_update and not wants_running:
        title = "Model update / version information"
    elif wants_running:
        title = "Model currently in use"

    intro = (
        "<p>This assistant uses a local LLM for open-ended questions. "
        "Structured tree-complaint queries (counts, dates, districts) are answered "
        "from the dataset without AI when possible.</p>"
    )

    return (
        f'<section class="query-result"><h3>{title}</h3>'
        f"{intro}"
        f"<ul>"
        f"<li><strong>Provider:</strong> {provider}</li>"
        f"<li><strong>Chat model (.env):</strong> <code>{model}</code></li>"
        f"<li><strong>Report model (.env):</strong> "
        f"<code>{html.escape(str(info.get('report_model', '—')))}</code></li>"
        f"{resolved_html}"
        f"<li><strong>Ollama URL:</strong> <code>{base_url}</code></li>"
        f"<li><strong>Status:</strong> {status}</li>"
        f"{modified_line}"
        f"{size_line}"
        f"<li><strong>Chat timeout:</strong> {info.get('chat_timeout_seconds', '—')}s</li>"
        f"</ul>"
        f"{status_detail}"
        f"{available_line}"
        f"<p>To change the model, set <code>CHAT_MODEL</code> or <code>AI_MODEL</code> "
        f"in <code>.env</code> and restart the server.</p>"
        f"</section>"
    )


def build_chat_user_prompt(
    user_message: str,
    intent: str,
    data: dict[str, Any] | list[Any],
    *,
    normalized_message: str | None = None,
) -> str:
    """Build a standardized user prompt from intent + pre-computed data."""
    normalized = normalized_message or user_message
    typo_note = ""
    if normalized != user_message.strip():
        typo_note = (
            f"\nNormalized question (typos/phrasing fixed for analysis): {normalized}\n"
            "Interpret the user's intent from BOTH lines; prefer the normalized wording.\n"
        )

    return f"""User question (original): {user_message}
{typo_note}
Detected intent: {intent}

Pre-computed data (use exactly — do not recalculate):
{json.dumps(data, ensure_ascii=False, indent=2)}

Required HTML structure for intent "{intent}":
{INTENT_HTML_SCHEMA.get(intent, INTENT_HTML_SCHEMA["generic"])}

Generate the HTML response now."""


def build_open_chat_user_prompt(
    user_message: str,
    *,
    normalized_message: str | None = None,
) -> str:
    """Prompt for general / open questions — no dataset payload required."""
    normalized = normalized_message or user_message
    typo_note = ""
    if normalized != user_message.strip():
        typo_note = (
            f"\nNormalized question (typos fixed): {normalized}\n"
        )
    return f"""User question: {user_message}
{typo_note}
This is a general question (not a structured data lookup). Answer it directly and helpfully.
You may briefly note that this app can also analyse Hong Kong tree complaint data if relevant.

Required HTML structure:
{INTENT_HTML_SCHEMA["generic"]}

Generate the HTML response now."""

