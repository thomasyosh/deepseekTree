#!/usr/bin/env python3
"""Run the AI model evaluation suite and compare Ollama models.

Examples:
  python scripts/eval_models.py
  python scripts/eval_models.py --models deepseek-r1:7b,deepseek-r1:14b
  python scripts/eval_models.py --category count,rank
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config
from model_eval import build_eval_suite, compute_eval_facts, run_eval_for_model


def _build_html_report(
    models: list[str],
    results_by_model: dict[str, list[dict[str, object]]],
    facts: dict[str, object],
) -> str:
    case_ids = [r["case_id"] for r in next(iter(results_by_model.values()))]
    rows_html = []
    for cid in case_ids:
        sample = next(r for r in next(iter(results_by_model.values())) if r["case_id"] == cid)
        row_cells = "".join(
            f'<td class="{"pass" if next(r for r in results_by_model[m] if r["case_id"] == cid)["passed"] else "fail"}">'
            f'{"Pass" if next(r for r in results_by_model[m] if r["case_id"] == cid)["passed"] else "Fail"}</td>'
            for m in models
        )
        rows_html.append(
            f"<tr><td>{html.escape(str(sample['category']))}</td>"
            f"<td>{html.escape(str(sample['question'][:80]))}…</td>"
            f"{row_cells}</tr>"
        )

    summary_rows = ""
    for m in models:
        rs = results_by_model[m]
        passed = sum(1 for r in rs if r["passed"])
        total = len(rs)
        pct = round(100 * passed / max(total, 1), 1)
        avg_s = round(sum(float(r["elapsed_s"]) for r in rs) / max(total, 1), 1)
        summary_rows += (
            f"<tr><td><code>{html.escape(m)}</code></td>"
            f"<td>{passed}/{total}</td><td>{pct}%</td><td>{avg_s}s</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"/><title>Model evaluation report</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #f8fafc; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff; margin: 1rem 0; }}
  th, td {{ border: 1px solid #e5e7eb; padding: 0.5rem 0.75rem; text-align: left; font-size: 0.9rem; }}
  th {{ background: #f1f5f9; }}
  td.pass {{ color: #166534; font-weight: 600; }}
  td.fail {{ color: #b91c1c; font-weight: 600; }}
  h1 {{ font-size: 1.35rem; }}
</style></head><body>
<h1>Model evaluation report</h1>
<p>Generated {html.escape(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))} ·
   Dataset: {facts.get("total_cases")} cases</p>
<h2>Summary</h2>
<table><thead><tr><th>Model</th><th>Passed</th><th>Accuracy</th><th>Avg time</th></tr></thead>
<tbody>{summary_rows}</tbody></table>
<h2>Per question</h2>
<table><thead><tr><th>Category</th><th>Question</th>
{"".join(f"<th>{html.escape(m)}</th>" for m in models)}
</tr></thead><tbody>{"".join(rows_html)}</tbody></table>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare LLM accuracy on tree-complaint eval suite")
    parser.add_argument(
        "--models",
        default=config.CHAT_MODEL,
        help="Comma-separated Ollama model names (default: CHAT_MODEL from .env)",
    )
    parser.add_argument(
        "--category",
        default="",
        help="Optional filter: count,rank,compare,date,narrative (comma-separated)",
    )
    parser.add_argument("--output", default=str(ROOT / "eval_results.json"))
    parser.add_argument("--html", default=str(ROOT / "eval_report.html"))
    args = parser.parse_args()

    if not config.DATA_PATH.exists():
        print(f"Missing {config.DATA_PATH}", file=sys.stderr)
        return 1

    rows = json.loads(config.DATA_PATH.read_text(encoding="utf-8"))
    facts = compute_eval_facts(rows)
    suite = build_eval_suite(rows)
    if args.category.strip():
        allowed = {c.strip() for c in args.category.split(",") if c.strip()}
        suite = [c for c in suite if c.category in allowed]

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    results_by_model: dict[str, list[dict[str, object]]] = {}

    for model in models:
        print(f"\n=== Evaluating {model} ({len(suite)} questions) ===")
        results = run_eval_for_model(rows, model, cases=suite)
        passed = sum(1 for r in results if r.passed)
        print(f"Score: {passed}/{len(results)} ({round(100*passed/max(len(results),1),1)}%)")
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            print(f"  [{mark}] {r.case_id}: {r.detail[:70]}")
        results_by_model[model] = [asdict(r) for r in results]

    out_path = Path(args.output)
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "dataset_cases": facts.get("total_cases"),
                "models": models,
                "results": results_by_model,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    html_path = Path(args.html)
    html_path.write_text(_build_html_report(models, results_by_model, facts), encoding="utf-8")
    print(f"\nWrote {out_path}")
    print(f"Wrote {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
