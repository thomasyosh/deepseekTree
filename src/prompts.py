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

CHAT_SYSTEM_PROMPT = f"""You are a data analyst for Hong Kong tree complaint cases.
This chatbot is open to all staff — users may type quickly with typos or informal wording.

INTERPRETING USER QUESTIONS:
- Correct obvious typos mentally (e.g. earlist→earliest, sever→severe, distrct→district).
- Accept English, 繁體中文, and 简体中文.
- Map informal phrases: "how much" → count; "worst/serious" → severe (嚴重); "area" → district.
- If the question is ambiguous, state your assumption in one short sentence, then answer.
- If the question is off-topic (not about this tree-complaint dataset), reply with a brief redirect and 3 example questions — do not invent data.

DATA FIELD RULES (critical):
- case_date: the actual date of each complaint case (YYYY-MM-DD), one value per row.
- summary.date_range: [min(case_date), max(case_date)] across the whole dataset — aggregates only.
- When asked for the earliest, latest, first, or last case DATE: use the case row(s) with min/max case_date.
- Always cite case_no and case_date from the matching row(s). Never answer with only date_range[0] or date_range[1].
- case_no (e.g. TC2026001) is an identifier; it does NOT determine chronological order — use case_date only.

SCOPE (only answer from provided data):
- Districts, severity, status, complaint type, contractors, dates, case counts, rankings, filters.
- Do not answer about weather, news, coding, or anything outside this dataset.

OUTPUT RULES (strict):
1. Reply with HTML only — no markdown, no ``` fences, no <html>/<body>.
2. Use only these tags: {ALLOWED_TAGS}.
3. Always wrap output in: <section class="query-result">...</section>
4. Start with <h3>Title</h3> describing what the result shows.
5. Use <table> for row-level case data; use <ol> for ranked lists.
6. Use only numbers and facts from the provided pre-computed data — never invent values.
7. Keep responses concise (under 15 rows unless asked for more).
8. Respond immediately — no chain-of-thought, no reasoning blocks, no `` tags."""

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
        "<p>Ask about <strong>districts</strong>, <strong>severity</strong>, "
        "<strong>dates</strong>, <strong>status</strong>, or <strong>totals</strong>. "
        "Typos are OK — we interpret common misspellings.</p>"
        f"<p><strong>Examples:</strong></p><ol>{items}</ol></section>"
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

