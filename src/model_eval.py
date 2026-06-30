"""AI model evaluation suite — ground-truth scoring for comparing LLM performance."""
from __future__ import annotations

import html
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

import config
import deepseek
import llm_client
from summary import build_summary

# Strip HTML/tags for numeric checks on model replies.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class EvalCase:
    id: str
    category: str
    question: str
    expected_hint: str
    scorer: Callable[[str, dict[str, Any]], tuple[bool, str]]
    difficulty: str = "medium"  # easy | medium | hard


def _plain(text: str) -> str:
    t = _TAG_RE.sub(" ", text or "")
    t = html.unescape(t)
    return _WS_RE.sub(" ", t).strip()


def _numbers_in(text: str) -> list[float]:
    found: list[float] = []
    for m in re.finditer(r"-?\d+(?:\.\d+)?", _plain(text)):
        try:
            found.append(float(m.group()))
        except ValueError:
            continue
    return found


def _contains_all(reply: str, tokens: list[str]) -> tuple[bool, str]:
    plain = _plain(reply).lower()
    missing = [t for t in tokens if t.lower() not in plain and t not in reply]
    if missing:
        return False, f"Missing: {', '.join(missing)}"
    return True, "All required values present"


def _expect_number(reply: str, expected: int | float, *, tolerance: float = 0.05) -> tuple[bool, str]:
    nums = _numbers_in(reply)
    if not nums:
        return False, f"No numbers found; expected {expected}"
    for n in nums:
        if isinstance(expected, int) and n == expected:
            return True, f"Found exact integer {expected}"
        if abs(n - expected) <= tolerance:
            return True, f"Found {n} ≈ {expected}"
    return False, f"Expected {expected}; found numbers {nums[:8]}"


def _expect_any_number(reply: str, options: list[int | float]) -> tuple[bool, str]:
    for opt in options:
        ok, msg = _expect_number(reply, opt, tolerance=0.01)
        if ok:
            return True, msg
    return False, f"Expected one of {options}; found {_numbers_in(reply)[:8]}"


def _expect_name(reply: str, name: str) -> tuple[bool, str]:
    if name in reply or name in _plain(reply):
        return True, f"Found {name!r}"
    return False, f"Expected name {name!r}"


def compute_eval_facts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = build_summary(rows)
    by_dist = Counter(summary.get("by_district", {}))
    by_complaint = Counter(summary.get("by_complaint_type", {}))
    by_contractor = Counter(summary.get("by_contractor", {}))
    by_severity = Counter(summary.get("by_severity", {}))
    by_status = Counter(summary.get("by_status", {}))

    dist_ranked = by_dist.most_common()
    top_districts = [n for n, _ in dist_ranked[:2]]
    complaint_ranked = by_complaint.most_common()
    contractor_ranked = by_contractor.most_common()

    sorted_rows = sorted(rows, key=lambda r: (r.get("case_date", ""), r.get("case_no", "")))
    earliest = sorted_rows[0] if sorted_rows else {}
    latest = sorted_rows[-1] if sorted_rows else {}

    severe_n = by_severity.get("嚴重", 0)
    mild_n = by_severity.get("輕微", 0)
    moderate_n = by_severity.get("中等", 0)

    sha_tin = sum(1 for r in rows if r.get("district") == "沙田")
    kowloon_city = sum(1 for r in rows if r.get("district") == "九龍城")

    june_2026 = sum(
        1 for r in rows if str(r.get("case_date", "")).startswith("2026-06")
    )
    dec_2025 = sum(
        1 for r in rows if str(r.get("case_date", "")).startswith("2025-12")
    )
    severe_dec_2025 = sum(
        1
        for r in rows
        if str(r.get("case_date", "")).startswith("2025-12")
        and r.get("severity") == "嚴重"
    )
    severe_h1_2026 = sum(
        1
        for r in rows
        if str(r.get("case_date", "")) >= "2026-01-01"
        and str(r.get("case_date", "")) <= "2026-06-30"
        and r.get("severity") == "嚴重"
    )

    fewest_contractor = contractor_ranked[-1] if contractor_ranked else ("—", 0)

    return {
        "summary": summary,
        "total_cases": summary.get("total_cases", 0),
        "total_trees": summary.get("total_trees", 0),
        "unique_districts": len(by_dist),
        "avg_trees": round(summary.get("total_trees", 0) / max(summary.get("total_cases", 1), 1), 2),
        "dist_second": dist_ranked[1] if len(dist_ranked) > 1 else ("—", 0),
        "complaint_top": complaint_ranked[0] if complaint_ranked else ("—", 0),
        "complaint_second": complaint_ranked[1] if len(complaint_ranked) > 1 else ("—", 0),
        "complaint_third": complaint_ranked[2] if len(complaint_ranked) > 2 else ("—", 0),
        "contractor_top": contractor_ranked[0] if contractor_ranked else ("—", 0),
        "contractor_fewest": fewest_contractor,
        "severe_n": severe_n,
        "mild_n": mild_n,
        "moderate_n": moderate_n,
        "status_new": by_status.get("新個案", 0),
        "status_done": by_status.get("已完成", 0),
        "sha_tin": sha_tin,
        "kowloon_city": kowloon_city,
        "june_2026": june_2026,
        "dec_2025": dec_2025,
        "severe_dec_2025": severe_dec_2025,
        "severe_h1_2026": severe_h1_2026,
        "earliest": earliest,
        "latest": latest,
        "date_range": summary.get("date_range", ["—", "—"]),
        "top_districts": top_districts,
    }


def build_eval_suite(rows: list[dict[str, Any]]) -> list[EvalCase]:
    """Question bank for LLM-only evaluation (bypasses local query engine)."""
    f = compute_eval_facts(rows)
    d2_name, d2_count = f["dist_second"]
    c2_name, c2_count = f["complaint_second"]
    c3_name, c3_count = f["complaint_third"]
    few_name, few_count = f["contractor_fewest"]
    earliest = f["earliest"]
    latest = f["latest"]

    def n(reply: str, _f: dict[str, Any], val: int | float) -> tuple[bool, str]:
        return _expect_number(reply, val)

    suite: list[EvalCase] = [
        EvalCase(
            "e01-total-cases",
            "count",
            "How many tree complaint cases are in this dataset in total?",
            str(f["total_cases"]),
            lambda r, _: n(r, _, f["total_cases"]),
            "easy",
        ),
        EvalCase(
            "e02-second-district",
            "rank",
            "Which district has the second-highest number of cases, and how many cases does it have?",
            f"{d2_name} ({d2_count})",
            lambda r, _: _contains_all(r, [d2_name, str(d2_count)]),
            "medium",
        ),
        EvalCase(
            "e03-third-complaint",
            "rank",
            "What is the third most common complaint type and its case count?",
            f"{c3_name} ({c3_count})",
            lambda r, _: _contains_all(r, [c3_name, str(c3_count)]),
            "hard",
        ),
        EvalCase(
            "e04-severe-count",
            "count",
            "How many cases are classified as 嚴重 (severe)?",
            str(f["severe_n"]),
            lambda r, _: n(r, _, f["severe_n"]),
            "easy",
        ),
        EvalCase(
            "e05-severe-vs-mild",
            "compare",
            "Are there more 嚴重 cases or 輕微 cases? Give both counts.",
            f"嚴重 {f['severe_n']} vs 輕微 {f['mild_n']}",
            lambda r, _: _contains_all(r, [str(f["severe_n"]), str(f["mild_n"])]),
            "medium",
        ),
        EvalCase(
            "e06-sha-tin-vs-kowloon",
            "compare",
            "Between 沙田 and 九龍城, which district has more cases? State both counts.",
            f"沙田 {f['sha_tin']} vs 九龍城 {f['kowloon_city']}",
            lambda r, _: _contains_all(r, ["沙田", "九龍城", str(max(f["sha_tin"], f["kowloon_city"]))]),
            "medium",
        ),
        EvalCase(
            "e07-june-2026",
            "date",
            "How many cases have case_date in June 2026 (2026-06)?",
            str(f["june_2026"]),
            lambda r, _: n(r, _, f["june_2026"]),
            "medium",
        ),
        EvalCase(
            "e08-fewest-contractor",
            "rank",
            "Which contractor has the fewest cases, and how many?",
            f"{few_name} ({few_count})",
            lambda r, _: _contains_all(r, [few_name, str(few_count)]),
            "hard",
        ),
        EvalCase(
            "e09-earliest-case",
            "date",
            f"What is the earliest case_date and case_no in the dataset?",
            f"{earliest.get('case_date')} / {earliest.get('case_no')}",
            lambda r, _: _contains_all(
                r, [str(earliest.get("case_date", "")), str(earliest.get("case_no", ""))]
            ),
            "medium",
        ),
        EvalCase(
            "e10-latest-case",
            "date",
            f"What is the latest case_date and case_no?",
            f"{latest.get('case_date')} / {latest.get('case_no')}",
            lambda r, _: _contains_all(
                r, [str(latest.get("case_date", "")), str(latest.get("case_no", ""))]
            ),
            "medium",
        ),
        EvalCase(
            "e11-status-new",
            "count",
            "How many cases have status 新個案?",
            str(f["status_new"]),
            lambda r, _: n(r, _, f["status_new"]),
            "easy",
        ),
        EvalCase(
            "e12-avg-trees",
            "ratio",
            "Calculate the average number of trees per case (total trees divided by total cases).",
            str(f["avg_trees"]),
            lambda r, _: _expect_any_number(r, [f["avg_trees"], round(f["avg_trees"], 1)]),
            "medium",
        ),
        EvalCase(
            "e13-dec-2025-severe",
            "date",
            "How many 嚴重 cases have case_date in December 2025?",
            str(f["severe_dec_2025"]),
            lambda r, _: n(r, _, f["severe_dec_2025"]),
            "hard",
        ),
        EvalCase(
            "e14-h1-2026-severe",
            "date",
            "How many 嚴重 cases occurred in the first half of 2026 (Jan–Jun)?",
            str(f["severe_h1_2026"]),
            lambda r, _: n(r, _, f["severe_h1_2026"]),
            "hard",
        ),
        EvalCase(
            "e15-second-complaint",
            "rank",
            "Name the second most frequent complaint type and its count.",
            f"{c2_name} ({c2_count})",
            lambda r, _: _contains_all(r, [c2_name, str(c2_count)]),
            "medium",
        ),
        EvalCase(
            "n01-briefing",
            "narrative",
            "Write a short manager briefing (3–5 sentences) on case volume, severity mix, and geographic hotspots.",
            f"Must cite ~{f['total_cases']} cases and 嚴重 {f['severe_n']}",
            lambda r, _: _contains_all(r, [str(f["total_cases"]), str(f["severe_n"])]),
            "medium",
        ),
        EvalCase(
            "n02-trend",
            "narrative",
            "In plain language, describe whether complaint types are evenly distributed or dominated by a few types.",
            "Should reference top complaint counts without inventing huge gaps",
            lambda r, _: (
                (_expect_name(r, f["complaint_top"][0])[0] and len(_plain(r)) > 80),
                "Mentions leading complaint type and has substantive prose",
            ),
            "medium",
        ),
        EvalCase(
            "n03-2025-2026",
            "reasoning",
            "Explain why case counts in 2025 look much lower than 2026 in this dataset.",
            f"Date range {f['date_range'][0]} → {f['date_range'][1]}",
            lambda r, _: (
                len(_plain(r)) > 60 and ("2025" in r or "2025" in _plain(r)),
                "Explains calendar coverage / date range",
            ),
            "medium",
        ),
        EvalCase(
            "n04-recommendation",
            "narrative",
            "Based on the data, which two districts would you prioritise for tree inspection and why?",
            "Should name real top districts with reasoning",
            lambda r, _: _contains_all(r, f.get("top_districts", [])),
            "hard",
        ),
    ]
    return suite


def build_eval_messages(
    rows: list[dict[str, Any]],
    question: str,
    history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Same prompt path as production chat, but always builds an LLM prompt."""
    summary = build_summary(rows)
    return deepseek.build_chat_messages(summary, history or [], question, rows=rows)


@dataclass
class EvalResult:
    case_id: str
    category: str
    question: str
    model: str
    passed: bool
    detail: str
    reply: str
    elapsed_s: float = 0.0


def score_eval_reply(case: EvalCase, reply: str, facts: dict[str, Any]) -> tuple[bool, str]:
    try:
        return case.scorer(reply, facts)
    except Exception as e:
        return False, f"Scorer error: {e}"


def run_eval_for_model(
    rows: list[dict[str, Any]],
    model: str,
    *,
    timeout: int | None = None,
    cases: list[EvalCase] | None = None,
) -> list[EvalResult]:
    import time

    facts = compute_eval_facts(rows)
    suite = cases or build_eval_suite(rows)
    results: list[EvalResult] = []

    for case in suite:
        messages = build_eval_messages(rows, case.question)
        started = time.monotonic()
        try:
            reply = llm_client.chat_completion(
                messages,
                model=model,
                max_tokens=config.CHAT_MAX_TOKENS,
                timeout=timeout or config.CHAT_TIMEOUT,
            )
            reply = llm_client.sanitize_chat_reply(reply)
        except Exception as e:
            reply = f"<p>Error: {html.escape(str(e))}</p>"
            passed, detail = False, str(e)
            elapsed = time.monotonic() - started
            results.append(
                EvalResult(
                    case.id, case.category, case.question, model,
                    passed, detail, reply, elapsed,
                )
            )
            continue

        passed, detail = score_eval_reply(case, reply, facts)
        elapsed = time.monotonic() - started
        results.append(
            EvalResult(
                case.id, case.category, case.question, model,
                passed, detail, reply, elapsed,
            )
        )
    return results
