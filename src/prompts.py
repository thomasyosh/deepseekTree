"""Standardized prompts for consistent HTML output."""

import json
from typing import Any

# Allowed HTML tags the model may use (enforced in system prompt).
ALLOWED_TAGS = "section, h3, p, table, thead, tbody, tr, th, td, ol, li, strong, em"

CHAT_SYSTEM_PROMPT = f"""You are a data analyst for Hong Kong tree complaint cases.

OUTPUT RULES (strict):
1. Reply with HTML only — no markdown, no ``` fences, no <html>/<body>.
2. Use only these tags: {ALLOWED_TAGS}.
3. Always wrap output in: <section class="query-result">...</section>
4. Start with <h3>Title</h3> describing what the result shows.
5. Use <table> for row-level case data; use <ol> for ranked lists.
6. Use only numbers and facts from the provided data — never invent values.
7. Keep responses concise (under 15 rows unless asked for more)."""

REPORT_SYSTEM_PROMPT = f"""You are a data analyst for Hong Kong tree complaint cases.

OUTPUT RULES (strict):
1. Write HTML only — no markdown, no ``` fences, no <html>/<head>/<body>.
2. Use only: p, h3, ul, li, strong, em, table, thead, tbody, tr, th, td.
3. Structure: executive summary, key trends, district hotspots, severity insights, recommendations.
4. Use only statistics from the provided summary — never invent numbers."""


def build_chat_user_prompt(
    user_message: str,
    intent: str,
    data: dict[str, Any] | list[Any],
) -> str:
    """Build a standardized user prompt from intent + pre-computed data."""
    return f"""User question: {user_message}

Detected intent: {intent}

Pre-computed data (use exactly — do not recalculate):
{json.dumps(data, ensure_ascii=False, indent=2)}

Required HTML structure for intent "{intent}":
{INTENT_HTML_SCHEMA.get(intent, INTENT_HTML_SCHEMA["generic"])}

Generate the HTML response now."""


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
    "generic": """
<section class="query-result">
  <h3>Answer</h3>
  <p>Concise answer using the pre-computed data.</p>
</section>""".strip(),
}
