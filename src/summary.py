from collections import Counter
from typing import Any


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"total_cases": 0}

    return {
        "total_cases": len(rows),
        "date_range": [
            min(r["case_date"] for r in rows),
            max(r["case_date"] for r in rows),
        ],
        "total_trees": sum(r.get("tree_count", 0) for r in rows),
        "by_district": dict(Counter(r["district"] for r in rows)),
        "by_status": dict(Counter(r["status"] for r in rows)),
        "by_severity": dict(Counter(r["severity"] for r in rows)),
        "by_complaint_type": dict(Counter(r["complaint_type"] for r in rows)),
        "by_contractor": dict(Counter(r["contractor"] for r in rows)),
        "by_tree_species": dict(Counter(r["tree_species"] for r in rows)),
    }


def filter_rows(rows: list[dict[str, Any]], keyword: str, limit: int = 10) -> list[dict[str, Any]]:
    keyword = keyword.strip().lower()
    if not keyword:
        return rows[:limit]

    matches = [
        row
        for row in rows
        if any(keyword in str(value).lower() for value in row.values())
    ]
    return matches[:limit]
