import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from query_engine import try_answer_locally
from prompts import CHAT_EXAMPLE_QUESTIONS
from summary import build_summary

rows = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
summary = build_summary(rows)

questions = [
    *CHAT_EXAMPLE_QUESTIONS,
    "What is the earliest case date?",
    "Top 5 districts by severe cases",
    "How many cases in 沙田?",
    "Show 5 newest cases",
    "Overview of the dataset",
    "In the month of 2025-12, what is the most Category of Complaint Type.",
    "What percentage of all cases are classified as 嚴重?",
    "How many unique districts appear in the dataset?",
    "What is the average number of trees per case?",
    "List contractors handling more than 5 cases.",
    "How many cases have status 新個案 versus 跟進中?",
    "Explain why 2025 has fewer cases than 2026 in this dataset.",
    "Describe the overall trend in complaint types across the dataset in plain language.",
    "Give me a narrative summary suitable for a manager briefing.",
    "What is the model currently running?",
    "Compare complaint types between 沙田 and 元朗.",
    "Which complaint type is most common among severe cases only?",
    "Are there more 嚴重 cases in the first half of 2026 than in December 2025?",
]

lines = []
for q in questions:
    local, _, _ = try_answer_locally(q, rows, summary)
    lines.append(f"{'LOCAL':6} | {q}" if local else f"{'AI':6} | {q}")

(ROOT / "_routing_audit.txt").write_text("\n".join(lines), encoding="utf-8")
print("done", len(questions))
