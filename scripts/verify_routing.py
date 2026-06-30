import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from query_engine import try_answer_locally
from testing_guide import _test_cases
from summary import build_summary

rows = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
s = build_summary(rows)
tests = _test_cases(rows, s, {})
for t in tests:
    ok = "OK" if t["route_ok"] == "yes" else "MISMATCH"
    print(f"{ok:8} intended={t['group']:5} route={t['route']:5} | {t['question'][:55]}")
