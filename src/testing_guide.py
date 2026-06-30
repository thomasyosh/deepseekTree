"""Build the model-accuracy testing panel for report.html from live dataset facts."""
from __future__ import annotations

import html
import json
from collections import Counter
from typing import Any

import config
from query_engine import try_answer_locally


def _load_rows() -> list[dict[str, Any]]:
    if not config.DATA_PATH.exists():
        return []
    data = json.loads(config.DATA_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _route_for(question: str, rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    local, _ = try_answer_locally(question, rows, summary)
    return "local" if local else "ai"


def _compute_facts(rows: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    if not rows:
        return {}

    sorted_rows = sorted(rows, key=lambda r: (r.get("case_date", ""), r.get("case_no", "")))
    severe = [r for r in rows if r.get("severity") == "嚴重"]
    contractors = Counter(r.get("contractor") for r in rows)
    big_contractors = [(n, c) for n, c in contractors.most_common() if c > 5]
    y2025 = sum(1 for r in rows if str(r.get("case_date", "")).startswith("2025"))
    y2026 = sum(1 for r in rows if str(r.get("case_date", "")).startswith("2026"))
    dec = [r for r in rows if str(r.get("case_date", "")).startswith("2025-12")]
    dec_complaints = Counter(r.get("complaint_type") for r in dec).most_common(1)
    severe_complaints = Counter(r.get("complaint_type") for r in severe).most_common(2)
    top_districts = Counter(summary.get("by_district", {})).most_common(3)
    avg_trees = summary.get("total_trees", 0) / max(summary.get("total_cases", 1), 1)

    return {
        "total_cases": summary.get("total_cases", 0),
        "total_trees": summary.get("total_trees", 0),
        "date_range": summary.get("date_range", ["—", "—"]),
        "unique_districts": len(summary.get("by_district", {})),
        "severity": summary.get("by_severity", {}),
        "severe_pct": round(100 * len(severe) / len(rows), 1),
        "avg_trees": round(avg_trees, 2),
        "earliest_case": sorted_rows[0].get("case_no"),
        "earliest_date": sorted_rows[0].get("case_date"),
        "latest_case": sorted_rows[-1].get("case_no"),
        "latest_date": sorted_rows[-1].get("case_date"),
        "contractors_over_5": big_contractors,
        "status_new": summary.get("by_status", {}).get("新個案", 0),
        "status_follow": summary.get("by_status", {}).get("跟進中", 0),
        "y2025": y2025,
        "y2026": y2026,
        "dec_count": len(dec),
        "dec_top_complaint": dec_complaints[0] if dec_complaints else None,
        "severe_top_complaints": severe_complaints,
        "top_districts": top_districts,
        "top_complaint_types": Counter(summary.get("by_complaint_type", {})).most_common(5),
    }


def _test_cases(rows: list[dict[str, Any]], summary: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, str]]:
    dr = facts.get("date_range", ["—", "—"])
    dec_top = facts.get("dec_top_complaint")
    dec_expected = (
        f"{dec_top[0]} ({dec_top[1]} of {facts.get('dec_count', 0)} cases in Dec 2025)"
        if dec_top
        else "—"
    )
    contractors = facts.get("contractors_over_5") or []
    contractor_expected = (
        f"{len(contractors)} contractors: "
        + ", ".join(f"{n} ({c})" for n, c in contractors)
        if contractors
        else "None above 5 cases"
    )
    severe_top = facts.get("severe_top_complaints") or []
    severe_complaint_note = (
        ", ".join(f"{n} ({c})" for n, c in severe_top) if severe_top else "—"
    )
    top_dist = ", ".join(f"{n} ({c})" for n, c in (facts.get("top_districts") or [])[:3])

    cases = [
        {
            "id": "local-earliest",
            "group": "local",
            "question": "What is the earliest case date?",
            "expected": (
                f"{facts.get('earliest_date')} (case {facts.get('earliest_case')})"
            ),
            "checks": "Status shows [local]. Uses case_date on a real row, not only date_range.",
        },
        {
            "id": "local-dec-complaint",
            "group": "local",
            "question": "In the month of 2025-12, what is the most Category of Complaint Type.",
            "expected": dec_expected,
            "checks": "Status shows [local]. Month filter 2025-12-01 → 2025-12-31 applied.",
        },
        {
            "id": "local-severe-pct",
            "group": "local",
            "question": "What percentage of all cases are classified as 嚴重?",
            "expected": f"{facts.get('severe_pct')}% ({facts.get('severity', {}).get('嚴重', 0)} of {facts.get('total_cases')})",
            "checks": "Status shows [local]. Should match severity table.",
        },
        {
            "id": "ai-districts",
            "group": "ai",
            "question": "How many unique districts appear in the dataset?",
            "expected": str(facts.get("unique_districts", "—")),
            "checks": "Status shows [ai]. Exact integer count.",
        },
        {
            "id": "ai-avg-trees",
            "group": "ai",
            "question": "What is the average number of trees per case?",
            "expected": (
                f"≈ {facts.get('avg_trees')} "
                f"({facts.get('total_trees')} trees ÷ {facts.get('total_cases')} cases)"
            ),
            "checks": "Status shows [ai]. Accept small rounding difference (e.g. 3.0 vs 3.04).",
        },
        {
            "id": "ai-contractors",
            "group": "ai",
            "question": "List contractors handling more than 5 cases.",
            "expected": contractor_expected,
            "checks": "Status shows [ai]. All listed names must have count > 5.",
        },
        {
            "id": "ai-status-compare",
            "group": "ai",
            "question": "How many cases have status 新個案 versus 跟進中?",
            "expected": (
                f"新個案: {facts.get('status_new')}, "
                f"跟進中: {facts.get('status_follow')}"
            ),
            "checks": "Status shows [ai]. Dataset has no status called 處理中.",
        },
        {
            "id": "ai-year-compare",
            "group": "ai",
            "question": "Explain why 2025 has fewer cases than 2026 in this dataset.",
            "expected": (
                f"2025: {facts.get('y2025')} cases; 2026: {facts.get('y2026')} cases. "
                f"Data spans {dr[0]} → {dr[1]} (mostly 2026)."
            ),
            "checks": "Status shows [ai]. Reasoning from dates; numbers must match.",
        },
        {
            "id": "narrative-trends",
            "group": "narrative",
            "question": "Describe the overall trend in complaint types across the dataset in plain language.",
            "expected": (
                "Top types are broadly similar in volume "
                + ", ".join(f"{n} ({c})" for n, c in (facts.get("top_complaint_types") or [])[:4])
                + ". Narrative should not invent large gaps."
            ),
            "checks": "Status shows [ai]. Qualitative — verify counts mentioned are plausible.",
        },
        {
            "id": "narrative-briefing",
            "group": "narrative",
            "question": "Give me a narrative summary suitable for a manager briefing.",
            "expected": (
                f"Should mention ~{facts.get('total_cases')} cases, "
                f"severity split (嚴重 {facts.get('severity', {}).get('嚴重', 0)}), "
                f"and busy districts e.g. {top_dist}."
            ),
            "checks": "Status shows [ai]. Numbers in prose must align with overview tables.",
        },
    ]

    for case in cases:
        case["route"] = _route_for(case["question"], rows, summary)
    return cases


def _badge(route: str) -> str:
    if route == "local":
        return '<span class="test-badge test-badge-local">local</span>'
    return '<span class="test-badge test-badge-ai">ai</span>'


def _group_label(group: str) -> str:
    labels = {
        "local": "Baseline (rule engine)",
        "ai": "AI — verifiable numbers",
        "narrative": "AI — narrative quality",
    }
    return labels.get(group, group)


def build_testing_guide_html(
    summary: dict[str, Any],
    rows: list[dict[str, Any]] | None = None,
) -> str:
    rows = rows if rows is not None else _load_rows()
    if not rows or not summary.get("total_cases"):
        return ""

    facts = _compute_facts(rows, summary)
    tests = _test_cases(rows, summary, facts)
    sev = facts.get("severity", {})

    fact_cards = "".join(
        f'<div class="test-stat"><span class="test-stat-label">{html.escape(label)}</span>'
        f'<span class="test-stat-value">{html.escape(str(value))}</span></div>'
        for label, value in [
            ("Cases", facts["total_cases"]),
            ("Trees", facts["total_trees"]),
            ("Districts", facts["unique_districts"]),
            ("嚴重", f"{sev.get('嚴重', 0)} ({facts['severe_pct']}%)"),
            ("Date range", f"{facts['date_range'][0]} → {facts['date_range'][1]}"),
            ("Avg trees / case", facts["avg_trees"]),
        ]
    )

    test_cards = []
    for i, t in enumerate(tests, 1):
        q_esc = html.escape(t["question"])
        test_cards.append(
            f'<article class="test-card" data-group="{html.escape(t["group"])}">'
            f'<div class="test-card-head">'
            f'<span class="test-card-num">{i}</span>'
            f'<span class="test-card-group">{html.escape(_group_label(t["group"]))}</span>'
            f'{_badge(t["route"])}'
            f"</div>"
            f'<p class="test-question">{q_esc}</p>'
            f'<button type="button" class="test-try-btn" data-question="{q_esc}">Try in chat</button>'
            f'<details class="test-answer-details">'
            f"<summary>Expected answer &amp; checks</summary>"
            f'<p class="test-expected"><strong>Expected:</strong> {html.escape(t["expected"])}</p>'
            f'<p class="test-checks"><strong>Pass if:</strong> {html.escape(t["checks"])}</p>'
            f'<p class="test-route-hint">Current routing: <code>[{html.escape(t["route"])}]</code> '
            f"(recomputed when this report was generated)</p>"
            f"</details>"
            f"</article>"
        )

    return f"""
    <section class="card test-guide" id="report-testing-guide">
      <details class="test-guide-panel" open>
        <summary class="test-guide-summary">
          <span class="test-guide-title">Model accuracy testing guide</span>
          <span class="test-guide-sub">Use chat to verify answers against live data.json facts</span>
        </summary>
        <div class="test-guide-body">
          <p class="test-intro">
            Ask each question in the chat panel. After the reply, check the status line:
            <span class="test-badge test-badge-local">local</span> = deterministic query engine;
            <span class="test-badge test-badge-ai">ai</span> = DeepSeek via Ollama.
            Expand each card for the expected answer computed from the current dataset.
          </p>
          <div class="test-stats-grid">{fact_cards}</div>
          <div class="test-toolbar">
            <label class="test-filter-label" for="test-filter">Show</label>
            <select id="test-filter" class="test-filter" aria-label="Filter test questions">
              <option value="all">All questions</option>
              <option value="local">Baseline (local) only</option>
              <option value="ai">AI verifiable only</option>
              <option value="narrative">AI narrative only</option>
            </select>
          </div>
          <div class="test-cards-grid" id="test-cards-grid">
            {"".join(test_cards)}
          </div>
          <p class="test-footnote">
            Severe-only top complaint types (reference):
            {html.escape(", ".join(f"{n} ({c})" for n, c in (facts.get("severe_top_complaints") or [])))}.
            Re-generate this report after refreshing data to update expected values.
          </p>
        </div>
      </details>
    </section>
    """
