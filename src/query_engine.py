import html
import re
from collections import Counter
from enum import Enum
from typing import Any

from prompts import build_chat_user_prompt


class Intent(str, Enum):
    RANK = "rank"
    SORT_CASES = "sort_cases"
    FILTER = "filter"
    OVERVIEW = "overview"
    UNKNOWN = "generic"


CASE_COLUMNS = ("case_no", "case_date", "district", "severity", "status", "complaint_type")


def detect_intent(message: str, rows: list[dict[str, Any]] | None = None) -> Intent:
    lower = message.lower()

    if rows and _extract_district(message, rows):
        return Intent.FILTER

    if any(t in lower for t in ("overview", "summary", "total", "概覽", "概况", "總數")):
        return Intent.OVERVIEW

    if any(
        t in lower or t in message
        for t in ("newest", "latest", "recent", "oldest", "最新", "最近", "最舊", "排序", "sort", "order")
    ):
        return Intent.SORT_CASES

    if any(
        t in lower or t in message
        for t in ("top", "前", "rank", "most", "highest", "grep", "filter", "嚴重", "serious", "severe")
    ):
        if any(t in lower or t in message for t in ("case", "個案", "记录", "記錄", "list", "列表")):
            return Intent.FILTER
        return Intent.RANK

    if any(t in lower or t in message for t in ("show", "list", "find", "列出", "顯示", "查找")):
        return Intent.FILTER

    return Intent.UNKNOWN


def _extract_limit(message: str, default: int = 5) -> int:
    match = re.search(r"(?:top|前|latest|newest|最近)\s*(\d+)", message, re.IGNORECASE)
    if match:
        return max(1, min(int(match.group(1)), 20))
    return default


def _wants_severe(message: str) -> bool:
    lower = message.lower()
    return any(t in lower or t in message for t in ("serious", "severe", "嚴重", "严重"))


def _wants_district(message: str) -> bool:
    lower = message.lower()
    return any(t in lower or t in message for t in ("district", "area", "區", "地区", "地區", "區域"))


def _wants_newest(message: str) -> bool:
    lower = message.lower()
    return any(t in lower or t in message for t in ("newest", "latest", "recent", "最新", "最近"))


def _extract_district(message: str, rows: list[dict[str, Any]]) -> str | None:
    """Match a known district name embedded in the user message."""
    districts = sorted({r["district"] for r in rows}, key=len, reverse=True)
    for district in districts:
        if district in message:
            return district
    return None


def _filter_by_district(
    rows: list[dict[str, Any]], message: str, district: str, limit: int
) -> list[dict[str, Any]]:
    filtered = [r for r in rows if r.get("district") == district]
    if _wants_severe(message):
        filtered = [r for r in filtered if r.get("severity") == "嚴重"]
    return sorted(filtered, key=lambda r: r.get("case_date", ""), reverse=True)[:limit]


def _district_summary_html(
    district: str, cases: list[dict[str, Any]], all_in_district: list[dict[str, Any]]
) -> str:
    severe_count = sum(1 for r in all_in_district if r.get("severity") == "嚴重")
    return (
        f'<section class="query-result"><h3>{html.escape(district)}</h3>'
        f"<ul>"
        f"<li><strong>Total cases:</strong> {len(all_in_district)}</li>"
        f"<li><strong>Serious cases (嚴重):</strong> {severe_count}</li>"
        f"</ul></section>"
    )


def _ranking_html(title: str, items: list[tuple[str, int]]) -> str:
    if not items:
        return (
            f'<section class="query-result"><h3>{html.escape(title)}</h3>'
            f"<p>No matching data.</p></section>"
        )
    rows = "".join(
        f"<li><strong>{html.escape(name)}</strong>: {count} cases</li>"
        for name, count in items
    )
    return (
        f'<section class="query-result"><h3>{html.escape(title)}</h3>'
        f"<ol>{rows}</ol></section>"
    )


def _cases_table_html(title: str, cases: list[dict[str, Any]]) -> str:
    if not cases:
        return (
            f'<section class="query-result"><h3>{html.escape(title)}</h3>'
            f"<p>No matching cases.</p></section>"
        )

    header = "".join(f"<th>{html.escape(col.replace('_', ' ').title())}</th>" for col in CASE_COLUMNS)
    body_rows = []
    for i, case in enumerate(cases, 1):
        cells = "".join(
            f"<td>{html.escape(str(case.get(col, '—')))}</td>" for col in CASE_COLUMNS
        )
        body_rows.append(f"<tr><td>{i}</td>{cells}</tr>")

    return (
        f'<section class="query-result"><h3>{html.escape(title)}</h3>'
        f"<p>Showing <strong>{len(cases)}</strong> case(s).</p>"
        f"<table><thead><tr><th>#</th>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table></section>"
    )


def _sort_cases(
    rows: list[dict[str, Any]], message: str, limit: int, district: str | None = None
) -> list[dict[str, Any]]:
    reverse = _wants_newest(message) or not any(
        t in message.lower() or t in message for t in ("oldest", "最舊", "earliest")
    )
    filtered = list(rows)
    if district:
        filtered = [r for r in filtered if r.get("district") == district]
    if _wants_severe(message):
        filtered = [r for r in filtered if r.get("severity") == "嚴重"]
    return sorted(filtered, key=lambda r: r.get("case_date", ""), reverse=reverse)[:limit]


def _rank_districts(rows: list[dict[str, Any]], message: str, limit: int) -> list[tuple[str, int]]:
    if _wants_severe(message):
        counts = Counter(r["district"] for r in rows if r.get("severity") == "嚴重")
        return counts.most_common(limit)
    counts = Counter(r["district"] for r in rows)
    return counts.most_common(limit)


def execute_query(
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[str | None, Intent, dict[str, Any] | list[Any] | None]:
    """
    Run a structured query. Returns (html_or_none, intent, data_for_llm_fallback).
    If html is not None, use it directly. Otherwise pass intent+data to LLM with standardized prompt.
    """
    intent = detect_intent(message, rows)
    limit = _extract_limit(message)

    district = _extract_district(message, rows)
    if district:
        all_in_district = [r for r in rows if r.get("district") == district]
        cases = _filter_by_district(rows, message, district, limit)
        if _wants_severe(message):
            title = f"Serious cases (嚴重) in {district}"
        else:
            title = f"Cases in {district}"
        summary_block = _district_summary_html(district, cases, all_in_district)
        table_block = _cases_table_html(title, cases)
        return summary_block + table_block, Intent.FILTER, cases

    if intent == Intent.OVERVIEW:
        data = {
            "total_cases": summary.get("total_cases", 0),
            "total_trees": summary.get("total_trees", 0),
            "date_range": summary.get("date_range"),
            "by_severity": summary.get("by_severity", {}),
            "by_status": summary.get("by_status", {}),
        }
        html_out = (
            '<section class="query-result"><h3>Dataset Overview</h3><ul>'
            f"<li><strong>Total cases:</strong> {data['total_cases']}</li>"
            f"<li><strong>Total trees:</strong> {data['total_trees']}</li>"
            f"<li><strong>Date range:</strong> {data['date_range'][0]} → {data['date_range'][1]}</li>"
            f"<li><strong>Serious (嚴重):</strong> {data['by_severity'].get('嚴重', 0)}</li>"
            "</ul></section>"
        )
        return html_out, intent, data

    if intent == Intent.SORT_CASES:
        cases = _sort_cases(rows, message, limit)
        order = "newest" if _wants_newest(message) else "oldest"
        title = f"{limit} {order} cases" + (" (嚴重 only)" if _wants_severe(message) else "")
        return _cases_table_html(title, cases), intent, cases

    if intent == Intent.RANK:
        if any(t in message for t in ("complaint", "投訴", "類型", "类型")):
            ranked = Counter(summary.get("by_complaint_type", {})).most_common(limit)
            title = f"Top {limit} complaint types"
            return _ranking_html(title, ranked), intent, ranked
        if any(t in message for t in ("status", "狀態", "状态")):
            ranked = Counter(summary.get("by_status", {})).most_common(limit)
            title = f"Top {limit} statuses"
            return _ranking_html(title, ranked), intent, ranked
        if any(t in message for t in ("contractor", "承辦商", "承办商")):
            ranked = Counter(summary.get("by_contractor", {})).most_common(limit)
            title = f"Top {limit} contractors"
            return _ranking_html(title, ranked), intent, ranked
        if any(t in message for t in ("species", "樹種", "树种")):
            ranked = Counter(summary.get("by_tree_species", {})).most_common(limit)
            title = f"Top {limit} tree species"
            return _ranking_html(title, ranked), intent, ranked
        if _wants_district(message) or _wants_severe(message) or "top" in message.lower() or "前" in message:
            ranked = _rank_districts(rows, message, limit)
            label = "serious cases (嚴重)" if _wants_severe(message) else "total cases"
            title = f"Top {limit} districts by {label}"
            return _ranking_html(title, ranked), intent, ranked

    if intent == Intent.FILTER and _wants_severe(message):
        cases = _sort_cases(rows, message, limit)
        return _cases_table_html(f"Top {limit} serious cases (嚴重)", cases), intent, cases

    return None, intent, None


def try_answer_locally(
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> str | None:
    html_out, _, _ = execute_query(message, rows, summary)
    return html_out


def build_llm_prompt(
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[str, dict[str, Any] | list[Any]] | None:
    """For unknown intents: pre-compute partial data and return standardized user prompt."""
    _, intent, data = execute_query(message, rows, summary)
    if data is None:
        data = {"summary": summary, "hint": "Answer from summary statistics only"}
    return build_chat_user_prompt(message, intent.value, data), data
