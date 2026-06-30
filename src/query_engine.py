import html
import re
import calendar
from collections import Counter
from datetime import date
from enum import Enum
from typing import Any

import llm_client

from chat_normalize import (
    fuzzy_match_district,
    is_probably_in_scope,
    is_probably_off_topic,
    is_system_meta_question,
    is_too_vague,
    normalize_user_message,
)
from prompts import (
    build_chat_user_prompt,
    build_chat_welcome_html,
    build_scope_redirect_html,
    build_system_meta_html,
)
from summary import build_summary

DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})")


class Intent(str, Enum):
    RANK = "rank"
    SORT_CASES = "sort_cases"
    FILTER = "filter"
    OVERVIEW = "overview"
    DATE_EXTREME = "date_extreme"
    UNKNOWN = "generic"


CASE_COLUMNS = ("case_no", "case_date", "district", "severity", "status", "complaint_type")


def detect_intent(message: str, rows: list[dict[str, Any]] | None = None) -> Intent:
    lower = message.lower()

    if rows and _extract_district(message, rows):
        return Intent.FILTER

    if _is_date_extreme_question(message):
        return Intent.DATE_EXTREME

    if any(t in lower for t in ("overview", "summary", "total", "概覽", "概况", "總數")):
        return Intent.OVERVIEW

    if any(
        t in lower or t in message
        for t in (
            "newest", "latest", "recent", "oldest", "earliest",
            "最新", "最近", "最舊", "最早", "排序", "sort", "order",
        )
    ):
        # "show only 2025 cases" must not be treated as a sort request.
        if not _has_period_filter(message):
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
        value = int(match.group(1))
        # Ignore 4-digit years (e.g. 2025) mistaken for a row limit.
        if 2000 <= value <= 2099 and re.search(rf"\b{value}\b", message):
            return default
        return max(1, min(value, 20))
    if re.search(r"\bmost\b", message, re.IGNORECASE):
        return 1
    return default


def _extract_month_filter(message: str) -> tuple[str | None, str | None]:
    """Parse YYYY-MM month ranges, e.g. 'month of 2025-12' or 'in 2025-12'."""
    patterns = [
        r"(?:month\s+of|in\s+(?:the\s+month\s+of)?|for)\s+(20\d{2})[-/](0[1-9]|1[0-2])\b",
        r"(?<![0-9-])(20\d{2})-(0[1-9]|1[0-2])(?![0-9])",
        r"(20\d{2})\s*年\s*(0?[1-9]|1[0-2])\s*月",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if not match:
            continue
        year, month = int(match.group(1)), int(match.group(2))
        last_day = calendar.monthrange(year, month)[1]
        return f"{year}-{month:02d}-01", f"{year}-{month:02d}-{last_day}"
    return None, None


def _rank_summary_key_from_message(message: str) -> tuple[str, str] | None:
    """Map a ranking question to a summary counter field and label."""
    lower = message.lower()
    if any(
        t in lower or t in message
        for t in ("complaint type", "complaint", "投訴", "類型", "类型", "category")
    ):
        return "by_complaint_type", "complaint types"
    if any(t in lower or t in message for t in ("status", "狀態", "状态")):
        return "by_status", "statuses"
    if any(t in lower or t in message for t in ("contractor", "承辦商", "承办商")):
        return "by_contractor", "contractors"
    if any(t in lower or t in message for t in ("species", "樹種", "树种", "tree species")):
        return "by_tree_species", "tree species"
    if _wants_district(message):
        return "by_district", "districts"
    if _wants_severe(message):
        return "by_severity", "severity levels"
    return None


def _ranking_title(
    label: str,
    limit: int,
    *,
    start: str | None = None,
    end: str | None = None,
) -> str:
    period = ""
    if start or end:
        period = f" ({start or '…'} → {end or '…'})"
    if limit == 1:
        singular = label[:-1] if label.endswith("s") else label
        return f"Most common {singular}{period}"
    return f"Top {limit} {label}{period}"


def _rank_from_summary(
    message: str,
    summary: dict[str, Any],
    *,
    start: str | None = None,
    end: str | None = None,
) -> tuple[str | None, list[tuple[str, int]] | None]:
    field = _rank_summary_key_from_message(message)
    if not field:
        return None, None
    key, label = field
    limit = _extract_limit(message)
    ranked = Counter(summary.get(key, {})).most_common(limit)
    title = _ranking_title(label, limit, start=start, end=end)
    return _ranking_html(title, ranked), ranked


def _has_period_filter(message: str) -> bool:
    start, end = _extract_date_range(message)
    return bool(start or end)


def _cases_for_period_report(
    rows: list[dict[str, Any]], message: str, *, max_rows: int = 100
) -> list[dict[str, Any]]:
    """All rows in the filtered period (not a capped sample), optional severity filter."""
    filtered = list(rows)
    if _wants_severe(message):
        filtered = [r for r in filtered if r.get("severity") == "嚴重"]
    return sorted(
        filtered,
        key=lambda r: (r.get("case_date", ""), r.get("case_no", "")),
        reverse=True,
    )[:max_rows]


def _wants_severe(message: str) -> bool:
    lower = message.lower()
    return any(t in lower or t in message for t in ("serious", "severe", "嚴重", "严重"))


def _wants_district(message: str) -> bool:
    lower = message.lower()
    return any(t in lower or t in message for t in ("district", "area", "區", "地区", "地區", "區域"))


def _wants_newest(message: str) -> bool:
    lower = message.lower()
    return any(t in lower or t in message for t in ("newest", "latest", "recent", "最新", "最近"))


def _wants_latest_date(message: str) -> bool:
    lower = message.lower()
    if any(
        t in lower or t in message
        for t in ("latest date", "last date", "most recent date", "newest date", "最新日期", "最晚日期")
    ):
        return True
    if any(t in lower or t in message for t in ("date", "日期", "day")):
        return any(
            t in lower or t in message
            for t in ("latest", "last", "newest", "most recent", "最新", "最遲", "最晚")
        )
    return False


def _wants_earliest_date(message: str) -> bool:
    lower = message.lower()
    if any(
        t in lower or t in message
        for t in ("earliest date", "first date", "oldest date", "minimum date", "最早日期", "最先日期")
    ):
        return True
    if any(t in lower or t in message for t in ("date", "日期", "day")):
        return any(
            t in lower or t in message
            for t in ("earliest", "first", "oldest", "minimum", "最早", "最舊", "最先")
        )
    return False


def _is_date_extreme_question(message: str) -> bool:
    """Single earliest/latest case_date questions — not multi-case sort lists."""
    if is_system_meta_question(message):
        return False
    lower = message.lower()
    if re.search(r"(?:top|前)\s*\d+", message, re.IGNORECASE):
        return False
    if re.search(r"\b\d+\s+(?:newest|latest|oldest|earliest)", lower):
        return False

    if _wants_earliest_date(message) or _wants_latest_date(message):
        return True

    asks_point_in_time = any(
        t in lower or t in message
        for t in (
            "what is", "what's", "when is", "when was", "which date",
            "什麼是", "什么是", "何時", "何时", "哪一天", "哪一個", "哪一个",
        )
    )
    has_extreme = any(
        t in lower or t in message
        for t in ("earliest", "latest", "first", "last", "oldest", "newest", "最早", "最舊", "最新", "最遲")
    )
    return asks_point_in_time and has_extreme


def _date_facts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    sorted_rows = sorted(
        rows,
        key=lambda r: (r.get("case_date", ""), r.get("case_no", "")),
    )
    earliest = sorted_rows[0]
    latest = sorted_rows[-1]
    return {
        "earliest_case_date": earliest.get("case_date"),
        "earliest_case": {col: earliest.get(col) for col in CASE_COLUMNS},
        "latest_case_date": latest.get("case_date"),
        "latest_case": {col: latest.get(col) for col in CASE_COLUMNS},
        "note": (
            "Use case_date on individual rows. summary.date_range is only [min, max] — "
            "always name the case_no for the row that has the earliest/latest case_date."
        ),
    }


def _extract_year_filter(message: str) -> tuple[str | None, str | None]:
    """Parse a calendar year (e.g. 2025) from natural language — not case_no tokens."""
    patterns = [
        r"(?:only|just|show|filter|display|adjust(?:\s+the)?\s+report(?:\s+to\s+show)?)\s+(?:only\s+)?(20\d{2})\b",
        r"\b(20\d{2})\s+cases?\b",
        r"cases?\s+(?:in|from|during)\s+(20\d{2})\b",
        r"(?:in|for|during)\s+(20\d{2})\b(?!\d)",
        r"\b(20\d{2})\s*年",
        r"year\s+(20\d{2})\b",
        r"(?:only|show|filter|display|adjust)\b.*?\b(20\d{2})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            year = int(match.group(1))
            if 2000 <= year <= 2099:
                return f"{year}-01-01", f"{year}-12-31"
    return None, None


def _extract_date_range(message: str) -> tuple[str | None, str | None]:
    """Parse start/end dates from free text. End defaults to today when requested."""
    year_range = _extract_year_filter(message)
    if year_range[0]:
        return year_range

    month_range = _extract_month_filter(message)
    if month_range[0]:
        return month_range

    lower = message.lower()
    today = date.today().isoformat()

    wants_today_end = any(
        t in lower or t in message
        for t in ("current date", "today", "現在", "目前", "今日", "當前", "今天")
    )

    range_match = re.search(
        r"(?:from|between|自|從|由)\s*(\d{4}-\d{2}-\d{2})\s*"
        r"(?:to|until|and|至|到|-)\s*"
        r"(\d{4}-\d{2}-\d{2}|current\s*date|today|現在|今日|今天)",
        message,
        re.IGNORECASE,
    )
    if range_match:
        start = range_match.group(1)
        end_raw = range_match.group(2).lower().replace(" ", "")
        end = today if end_raw in ("currentdate", "today", "現在", "今日", "今天") else range_match.group(2)
        return start, end

    dates = DATE_PATTERN.findall(message)
    if len(dates) >= 2:
        return dates[0], dates[1]

    if len(dates) == 1 and wants_today_end:
        return dates[0], today

    if len(dates) == 1 and any(
        t in lower for t in ("from", "since", "after", "starting", "自", "從", "由")
    ):
        return dates[0], today

    return None, None


def _apply_date_range(
    rows: list[dict[str, Any]], start: str | None, end: str | None
) -> list[dict[str, Any]]:
    filtered = rows
    if start:
        filtered = [r for r in filtered if r.get("case_date", "") >= start]
    if end:
        filtered = [r for r in filtered if r.get("case_date", "") <= end]
    return filtered


def _apply_message_filters(
    message: str, rows: list[dict[str, Any]], summary: dict[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    """Apply date filters from the message and rebuild summary for the filtered rows."""
    start, end = _extract_date_range(message)
    if not (start or end):
        return rows, summary, ""

    filtered = _apply_date_range(rows, start, end)
    filtered_summary = build_summary(filtered)
    effective_start = start or filtered_summary.get("date_range", ["—", "—"])[0]
    effective_end = end or filtered_summary.get("date_range", ["—", "—"])[1]
    banner = (
        '<section class="query-result"><p><strong>Date filter applied:</strong> '
        f"{html.escape(effective_start)} → {html.escape(effective_end)} "
        f"({filtered_summary.get('total_cases', 0)} cases)</p></section>"
    )
    return filtered, filtered_summary, banner


def _with_banner(banner: str, html_out: str) -> str:
    return banner + html_out if banner else html_out


def _extract_district(message: str, rows: list[dict[str, Any]]) -> str | None:
    """Match a known district name embedded in the user message (incl. fuzzy Latin)."""
    districts = {r["district"] for r in rows}
    return fuzzy_match_district(message, districts)


def try_system_meta_reply(message: str) -> str | None:
    """Answer questions about the LLM / app setup without calling the model."""
    if not is_system_meta_question(message):
        return None
    try:
        info = llm_client.get_runtime_model_info()
    except Exception as e:
        info = {
            "provider": "ollama",
            "chat_model": "unknown",
            "report_model": "unknown",
            "ollama_base_url": "",
            "ollama_ok": False,
            "health_error": str(e),
            "models_available": [],
        }
    return build_system_meta_html(info, message)


def try_preflight_reply(message: str) -> str | None:
    """Fast guidance for greetings, vague prompts, or clearly off-topic questions."""
    if is_too_vague(message):
        return build_chat_welcome_html()
    meta = try_system_meta_reply(message)
    if meta:
        return meta
    if is_probably_off_topic(message) and not is_probably_in_scope(message):
        return build_scope_redirect_html()
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
        t in message.lower() or t in message
        for t in ("oldest", "earliest", "最舊", "最早")
    )
    filtered = list(rows)
    if district:
        filtered = [r for r in filtered if r.get("district") == district]
    if _wants_severe(message):
        filtered = [r for r in filtered if r.get("severity") == "嚴重"]
    return sorted(filtered, key=lambda r: r.get("case_date", ""), reverse=reverse)[:limit]


def _overview_html(summary: dict[str, Any]) -> str:
    date_range = summary.get("date_range", ["—", "—"])
    return (
        '<section class="query-result"><h3>Dataset Overview</h3><ul>'
        f"<li><strong>Total cases:</strong> {summary.get('total_cases', 0)}</li>"
        f"<li><strong>Total trees:</strong> {summary.get('total_trees', 0)}</li>"
        f"<li><strong>Date range:</strong> {date_range[0]} → {date_range[1]}</li>"
        f"<li><strong>Serious (嚴重):</strong> "
        f"{summary.get('by_severity', {}).get('嚴重', 0)}</li>"
        "</ul></section>"
    )


def _period_report_html(
    summary: dict[str, Any],
    cases: list[dict[str, Any]],
    start: str | None,
    end: str | None,
) -> str:
    """Structured HTML for a date/year filtered slice of the dataset."""
    dr = summary.get("date_range", ["—", "—"])
    period = f"{start or dr[0]} → {end or dr[1]}"
    total = summary.get("total_cases", 0)
    shown = len(cases)
    districts = Counter(summary.get("by_district", {})).most_common(5)
    district_rows = "".join(
        f"<li><strong>{html.escape(name)}</strong>: {count} cases</li>"
        for name, count in districts
    ) or "<li>No cases in this period.</li>"
    severity = summary.get("by_severity", {})
    severity_rows = "".join(
        f"<li><strong>{html.escape(name)}</strong>: {count}</li>"
        for name, count in sorted(severity.items(), key=lambda item: item[1], reverse=True)
    ) or "<li>—</li>"
    status = summary.get("by_status", {})
    status_rows = "".join(
        f"<li><strong>{html.escape(name)}</strong>: {count}</li>"
        for name, count in sorted(status.items(), key=lambda item: item[1], reverse=True)[:5]
    ) or "<li>—</li>"

    return (
        f'<section class="query-result"><h3>Filtered report</h3>'
        f"<p>Found <strong>{total}</strong> cases where "
        f"<code>case_date</code> is between "
        f"<strong>{html.escape(period)}</strong>.</p>"
        f"<ul><li><strong>Total trees:</strong> {summary.get('total_trees', 0)}</li>"
        f"<li><strong>Listed below:</strong> {shown} case(s)</li></ul>"
        f"<h3>Top districts</h3><ol>{district_rows}</ol>"
        f"<h3>By severity</h3><ul>{severity_rows}</ul>"
        f"<h3>By status</h3><ul>{status_rows}</ul>"
        f"</section>"
        + _cases_table_html(
            f"All matching cases ({shown} of {total})",
            cases,
        )
    )


def _rank_districts(rows: list[dict[str, Any]], message: str, limit: int) -> list[tuple[str, int]]:
    if _wants_severe(message):
        counts = Counter(r["district"] for r in rows if r.get("severity") == "嚴重")
        return counts.most_common(limit)
    counts = Counter(r["district"] for r in rows)
    return counts.most_common(limit)


def _cases_on_extreme_date(
    rows: list[dict[str, Any]], want_latest: bool
) -> tuple[str, list[dict[str, Any]]]:
    sorted_rows = sorted(
        rows,
        key=lambda r: (r.get("case_date", ""), r.get("case_no", "")),
    )
    if not sorted_rows:
        return "", []
    extreme_date = (
        sorted_rows[-1].get("case_date", "")
        if want_latest
        else sorted_rows[0].get("case_date", "")
    )
    matches = [r for r in rows if r.get("case_date") == extreme_date]
    matches.sort(key=lambda r: r.get("case_no", ""))
    return extreme_date, matches


def _date_extreme_html(rows: list[dict[str, Any]], message: str) -> str:
    want_latest = _wants_latest_date(message) and not _wants_earliest_date(message)
    label = "Latest" if want_latest else "Earliest"
    extreme_date, cases = _cases_on_extreme_date(rows, want_latest)
    if not cases:
        return (
            '<section class="query-result"><h3>Case date</h3>'
            "<p>No cases in dataset.</p></section>"
        )

    lead = (
        f'<section class="query-result"><h3>{label} case date</h3>'
        f"<p>The <strong>{label.lower()}</strong> <code>case_date</code> in the dataset is "
        f"<strong>{html.escape(extreme_date)}</strong>"
    )
    if cases:
        lead += (
            f" (case <strong>{html.escape(str(cases[0].get('case_no', '—')))}</strong>"
            f"{f', +{len(cases) - 1} more on the same date' if len(cases) > 1 else ''})."
        )
    lead += "</p></section>"

    table_title = f"{label} case(s) by case_date"
    return lead + _cases_table_html(table_title, cases[:10])


def execute_query(
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[str | None, Intent, dict[str, Any] | list[Any] | None]:
    """
    Run a structured query. Returns (html_or_none, intent, data_for_llm_fallback).
    If html is not None, use it directly. Otherwise pass intent+data to LLM with standardized prompt.
    """
    rows, summary, banner = _apply_message_filters(message, rows, summary)
    start, end = _extract_date_range(message)

    if not rows and (banner or start or end):
        empty = (
            '<section class="query-result"><p>No cases found in the selected date range.</p></section>'
        )
        return _with_banner(banner, empty), Intent.FILTER, summary

    # Date filter + ranking (e.g. most complaint type in 2025-12).
    if banner or start or end:
        rank_html, ranked = _rank_from_summary(message, summary, start=start, end=end)
        if rank_html:
            return (
                _with_banner(banner, rank_html),
                Intent.RANK,
                summary if isinstance(summary, dict) else ranked,
            )

    # Year/date filters — return the full filtered set when no ranking was requested.
    if banner or start or end:
        cases = _cases_for_period_report(rows, message)
        body = _period_report_html(summary, cases, start, end)
        return _with_banner(banner, body), Intent.FILTER, summary

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
        return _with_banner(banner, summary_block + table_block), Intent.FILTER, cases

    if intent == Intent.OVERVIEW:
        data = {
            "total_cases": summary.get("total_cases", 0),
            "total_trees": summary.get("total_trees", 0),
            "date_range": summary.get("date_range"),
            "by_severity": summary.get("by_severity", {}),
            "by_status": summary.get("by_status", {}),
        }
        return _with_banner(banner, _overview_html(summary)), intent, data

    if intent == Intent.DATE_EXTREME:
        want_latest = _wants_latest_date(message) and not _wants_earliest_date(message)
        extreme_date, cases = _cases_on_extreme_date(rows, want_latest)
        data = {
            "extreme": "latest" if want_latest else "earliest",
            "case_date": extreme_date,
            "cases": [{col: c.get(col) for col in CASE_COLUMNS} for c in cases[:10]],
            **_date_facts(rows),
        }
        return (
            _with_banner(banner, _date_extreme_html(rows, message)),
            intent,
            data,
        )

    if intent == Intent.SORT_CASES:
        cases = _sort_cases(rows, message, limit)
        order = "newest" if _wants_newest(message) else "oldest"
        title = f"{limit} {order} cases" + (" (嚴重 only)" if _wants_severe(message) else "")
        return _with_banner(banner, _cases_table_html(title, cases)), intent, cases

    if intent == Intent.RANK:
        rank_html, ranked = _rank_from_summary(message, summary)
        if rank_html:
            return _with_banner(banner, rank_html), intent, ranked
        if _wants_district(message) or _wants_severe(message) or "top" in message.lower() or "前" in message:
            ranked = _rank_districts(rows, message, limit)
            label = "serious cases (嚴重)" if _wants_severe(message) else "total cases"
            title = f"Top {limit} districts by {label}"
            return _with_banner(banner, _ranking_html(title, ranked)), intent, ranked

    if intent == Intent.FILTER and _wants_severe(message):
        cases = _sort_cases(rows, message, limit)
        return (
            _with_banner(banner, _cases_table_html(f"Top {limit} serious cases (嚴重)", cases)),
            intent,
            cases,
        )

    return None, intent, None


def date_facts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return _date_facts(rows)


def try_answer_locally(
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    normalized = normalize_user_message(message)
    query_text = normalized or message.strip()

    preflight = try_preflight_reply(query_text)
    if preflight:
        return preflight, None

    html_out, _, data = execute_query(query_text, rows, summary)
    filtered_summary = data if isinstance(data, dict) and "total_cases" in data else None
    return html_out, filtered_summary


def build_llm_prompt(
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
) -> tuple[str, dict[str, Any] | list[Any]] | None:
    """For unknown intents: pre-compute partial data and return standardized user prompt."""
    normalized = normalize_user_message(message)
    query_text = normalized or message.strip()

    preflight = try_preflight_reply(query_text)
    if preflight:
        return None

    _, intent, data = execute_query(query_text, rows, summary)
    if data is None:
        _, filtered_summary, _ = _apply_message_filters(query_text, rows, summary)
        data = {
            "summary": filtered_summary,
            "date_facts": _date_facts(rows),
            "hint": (
                "Answer using case_date on individual case rows. "
                "Do not reply with only summary.date_range — cite case_no and case_date."
            ),
        }
    return (
        build_chat_user_prompt(
            message,
            intent.value,
            data,
            normalized_message=query_text if query_text != message.strip() else None,
        ),
        data,
    )
