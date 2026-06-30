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

    st = summary.get("by_status", {})
    sha_tin = [r for r in rows if r.get("district") == "沙田"]
    yuen_long = [r for r in rows if r.get("district") == "元朗"]
    st_complaints = Counter(r.get("complaint_type") for r in sha_tin).most_common(2)
    yl_complaints = Counter(r.get("complaint_type") for r in yuen_long).most_common(2)

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
        "status_new": st.get("新個案", 0),
        "status_follow": st.get("跟進中", 0),
        "y2025": y2025,
        "y2026": y2026,
        "dec_count": len(dec),
        "dec_top_complaint": dec_complaints[0] if dec_complaints else None,
        "severe_top_complaints": severe_complaints,
        "top_districts": top_districts,
        "top_complaint_types": Counter(summary.get("by_complaint_type", {})).most_common(5),
        "st_top_complaints": st_complaints,
        "yl_top_complaints": yl_complaints,
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
    top_dist = ", ".join(f"{n} ({c})" for n, c in (facts.get("top_districts") or [])[:3])
    st_top = facts.get("st_top_complaints") or []
    yl_top = facts.get("yl_top_complaints") or []
    district_compare_note = (
        f"沙田 top: {', '.join(f'{n} ({c})' for n, c in st_top[:2])}; "
        f"元朗 top: {', '.join(f'{n} ({c})' for n, c in yl_top[:2])}"
        if st_top or yl_top
        else "Side-by-side complaint rankings per district"
    )

    cases = [
        {
            "id": "local-earliest",
            "group": "local",
            "question": "What is the earliest case date?",
            "expected": f"{facts.get('earliest_date')} (case {facts.get('earliest_case')})",
            "checks": "[local] — date_extreme on case_date rows.",
        },
        {
            "id": "local-dec-complaint",
            "group": "local",
            "question": "In the month of 2025-12, what is the most Category of Complaint Type.",
            "expected": dec_expected,
            "checks": "[local] — month filter + ranked complaint type.",
        },
        {
            "id": "local-severe-pct",
            "group": "local",
            "question": "What percentage of all cases are classified as 嚴重?",
            "expected": (
                f"{facts.get('severe_pct')}% "
                f"({facts.get('severity', {}).get('嚴重', 0)} of {facts.get('total_cases')})"
            ),
            "checks": "[local] — severity aggregate.",
        },
        {
            "id": "local-contractors",
            "group": "local",
            "question": "List contractors handling more than 5 cases.",
            "expected": contractor_expected,
            "checks": "[local] — contractor threshold filter (>5).",
        },
        {
            "id": "local-districts-count",
            "group": "local",
            "question": "How many unique districts appear in the dataset?",
            "expected": str(facts.get("unique_districts", "—")),
            "checks": "[local] — exact district cardinality.",
        },
        {
            "id": "local-avg-trees",
            "group": "local",
            "question": "What is the average number of trees per case?",
            "expected": (
                f"{facts.get('avg_trees')} "
                f"({facts.get('total_trees')} ÷ {facts.get('total_cases')})"
            ),
            "checks": "[local] — total_trees / total_cases.",
        },
        {
            "id": "local-status-compare",
            "group": "local",
            "question": "How many cases have status 新個案 versus 跟進中?",
            "expected": (
                f"新個案: {facts.get('status_new')}, 跟進中: {facts.get('status_follow')}"
            ),
            "checks": "[local] — status A vs B counts (no 處理中 in this dataset).",
        },
        {
            "id": "local-year-compare",
            "group": "local",
            "question": "Explain why 2025 has fewer cases than 2026 in this dataset.",
            "expected": (
                f"2025: {facts.get('y2025')}; 2026: {facts.get('y2026')}; "
                f"range {dr[0]} → {dr[1]}"
            ),
            "checks": "[local] — templated explanation with exact year counts.",
        },
        {
            "id": "local-district-compare",
            "group": "local",
            "question": "Compare complaint types between 沙田 and 元朗.",
            "expected": district_compare_note,
            "checks": "[local] — top complaint types per district, both named.",
        },
        {
            "id": "ai-trends",
            "group": "ai",
            "question": "Describe the overall trend in complaint types across the dataset in plain language.",
            "expected": (
                "Prose summary; top types near "
                + ", ".join(f"{n} ({c})" for n, c in (facts.get("top_complaint_types") or [])[:4])
            ),
            "checks": "[ai] — narrative only; numbers cited should be plausible.",
        },
        {
            "id": "ai-briefing",
            "group": "ai",
            "question": "Give me a narrative summary suitable for a manager briefing.",
            "expected": (
                f"Prose (~{facts.get('total_cases')} cases, 嚴重 "
                f"{facts.get('severity', {}).get('嚴重', 0)}, districts e.g. {top_dist})"
            ),
            "checks": "[ai] — must not be a dry overview table only.",
        },
    ]

    for case in cases:
        case["route"] = _route_for(case["question"], rows, summary)
        case["route_ok"] = (
            "yes" if (case["group"] == "ai" and case["route"] == "ai")
            or (case["group"] == "local" and case["route"] == "local")
            else "review"
        )
    return cases


def _badge(route: str) -> str:
    if route == "local":
        return '<span class="test-badge test-badge-local">local</span>'
    return '<span class="test-badge test-badge-ai">ai</span>'


def _group_label(group: str) -> str:
    labels = {
        "local": "Local query engine",
        "ai": "AI model (DeepSeek)",
    }
    return labels.get(group, group)


def _routing_policy_html() -> str:
    return """
    <div class="test-policy">
      <h3>Routing policy</h3>
      <table class="test-policy-table">
        <thead>
          <tr><th>Route</th><th>Use when</th><th>Examples</th></tr>
        </thead>
        <tbody>
          <tr>
            <td><span class="test-badge test-badge-local">local</span></td>
            <td>Exact counts, filters, rankings, date/month/year slices, thresholds, comparisons with verifiable numbers</td>
            <td>Top districts, earliest date, % 嚴重, contractors &gt; 5, 新個案 vs 跟進中</td>
          </tr>
          <tr>
            <td><span class="test-badge test-badge-ai">ai</span></td>
            <td>Open-ended prose, manager briefings, qualitative trends, ambiguous wording not covered by rules</td>
            <td>Describe trends in plain language, narrative briefing, novel phrasing</td>
          </tr>
        </tbody>
      </table>
      <p class="test-policy-note">
        Status line after each chat message shows <code>[local]</code> or <code>[ai]</code>.
        For <strong>comparing models</strong> (e.g. 7b vs 14b), use the
        <strong>LLM evaluation battery</strong> below and run
        <code>python scripts/eval_models.py --models model-a,model-b</code>.
      </p>
    </div>
    """


def _difficulty_badge(level: str) -> str:
    return f'<span class="test-badge test-diff-{html.escape(level)}">{html.escape(level)}</span>'


def _model_eval_section_html(rows: list[dict[str, Any]]) -> str:
    from model_eval import build_eval_suite

    suite = build_eval_suite(rows)
    by_cat: dict[str, int] = {}
    for c in suite:
        by_cat[c.category] = by_cat.get(c.category, 0) + 1
    cat_summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_cat.items()))

    cards = []
    for i, case in enumerate(suite, 1):
        q_esc = html.escape(case.question)
        cards.append(
            f'<article class="test-card test-card-eval" data-group="eval" data-category="{html.escape(case.category)}">'
            f'<div class="test-card-head">'
            f'<span class="test-card-num">E{i}</span>'
            f'<span class="test-card-group">{html.escape(case.category)}</span>'
            f'{_difficulty_badge(case.difficulty)}'
            f'<span class="test-badge test-badge-ai">llm eval</span>'
            f"</div>"
            f'<p class="test-question">{q_esc}</p>'
            f'<details class="test-answer-details" open>'
            f"<summary>Ground truth (auto-scored)</summary>"
            f'<p class="test-expected"><strong>Expected:</strong> {html.escape(case.expected_hint)}</p>'
            f'<p class="test-checks">Scored automatically when you run <code>eval_models.py</code>.</p>'
            f"</details>"
            f"</article>"
        )

    return f"""
    <div class="test-eval-section">
      <h3>LLM evaluation battery ({len(suite)} questions)</h3>
      <p class="test-intro">
        These questions <strong>always call the model</strong> (not the local query engine) so you can
        compare accuracy across <code>CHAT_MODEL</code> settings — e.g.
        <code>deepseek-r1:7b</code> vs <code>deepseek-r1:14b</code>.
        Categories: {html.escape(cat_summary)}.
      </p>
      <ol class="test-eval-steps">
        <li>Ensure Ollama is running and models are pulled (<code>ollama pull …</code>).</li>
        <li>From project root:
          <code>python scripts/eval_models.py --models deepseek-r1:7b,deepseek-r1:14b</code></li>
        <li>Open <code>eval_report.html</code> for a side-by-side pass/fail matrix.</li>
        <li>Higher pass rate + reasonable latency = better model for this dataset.</li>
      </ol>
      <div class="test-toolbar">
        <label class="test-filter-label" for="test-eval-filter">Category</label>
        <select id="test-eval-filter" class="test-filter" aria-label="Filter eval questions">
          <option value="all">All ({len(suite)})</option>
          <option value="count">Count</option>
          <option value="rank">Rank</option>
          <option value="compare">Compare</option>
          <option value="date">Date</option>
          <option value="ratio">Ratio</option>
          <option value="narrative">Narrative</option>
          <option value="reasoning">Reasoning</option>
        </select>
      </div>
      <div class="test-cards-grid" id="test-eval-grid">
        {"".join(cards)}
      </div>
    </div>
    """


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
    route_issues = sum(1 for t in tests if t.get("route_ok") == "review")

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
        mismatch = ""
        if t.get("route_ok") == "review":
            mismatch = (
                '<span class="test-badge test-badge-warn" title="Routing differs from intended group">'
                "route mismatch</span>"
            )
        test_cards.append(
            f'<article class="test-card" data-group="{html.escape(t["group"])}">'
            f'<div class="test-card-head">'
            f'<span class="test-card-num">{i}</span>'
            f'<span class="test-card-group">{html.escape(_group_label(t["group"]))}</span>'
            f'{_badge(t["route"])}'
            f"{mismatch}"
            f"</div>"
            f'<p class="test-question">{q_esc}</p>'
            f'<button type="button" class="test-try-btn" data-question="{q_esc}">Try in chat</button>'
            f'<details class="test-answer-details">'
            f"<summary>Expected answer &amp; checks</summary>"
            f'<p class="test-expected"><strong>Expected:</strong> {html.escape(t["expected"])}</p>'
            f'<p class="test-checks"><strong>Pass if:</strong> {html.escape(t["checks"])}</p>'
            f'<p class="test-route-hint">Live routing: <code>[{html.escape(t["route"])}]</code></p>'
            f"</details>"
            f"</article>"
        )

    warn_banner = ""
    if route_issues:
        warn_banner = (
            f'<p class="test-warn-banner">{route_issues} question(s) routed differently than '
            f"intended — check query_engine rules after code changes.</p>"
        )

    return f"""
    <section class="card test-guide" id="report-testing-guide">
      <details class="test-guide-panel" open>
        <summary class="test-guide-summary">
          <span class="test-guide-title">Model accuracy testing guide</span>
          <span class="test-guide-sub">Local = exact data queries · AI = narrative / open-ended</span>
        </summary>
        <div class="test-guide-body">
          <p class="test-intro">
            Use this checklist while testing whether DeepSeek is suitable for your dataset.
            <span class="test-badge test-badge-local">local</span> answers are computed from
            <code>data.json</code> (fast, exact).
            <span class="test-badge test-badge-ai">ai</span> answers call Ollama (slower, judge prose quality).
          </p>
          {_routing_policy_html()}
          {warn_banner}
          <div class="test-stats-grid">{fact_cards}</div>
          <div class="test-toolbar">
            <label class="test-filter-label" for="test-filter">Show</label>
            <select id="test-filter" class="test-filter" aria-label="Filter test questions">
              <option value="all">All questions</option>
              <option value="local">Local query engine only</option>
              <option value="ai">AI model only</option>
            </select>
          </div>
          <div class="test-cards-grid" id="test-cards-grid">
            {"".join(test_cards)}
          </div>
          {_model_eval_section_html(rows)}
          <p class="test-footnote">
            Severe-only top complaint types (reference):
            {html.escape(", ".join(f"{n} ({c})" for n, c in (facts.get("severe_top_complaints") or [])))}.
            Reload the page after data refresh to recompute expected values.
          </p>
        </div>
      </details>
    </section>
    """
