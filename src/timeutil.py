"""Timezone helpers that work on Windows without extra IANA data."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

HK_OFFSET = timezone(timedelta(hours=8), name="Hong Kong")


def now_hong_kong() -> datetime:
    """Current time in Hong Kong (UTC+8)."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Hong_Kong"))
    except Exception:
        return datetime.now(HK_OFFSET)
