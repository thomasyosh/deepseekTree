"""Append-only log of chat questions and answers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
import filelogger


def log_chat(
    question: str,
    *,
    reply: str | None = None,
    source: str | None = None,
    record_count: int | None = None,
    error: str | None = None,
) -> None:
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
    }
    if reply is not None:
        entry["reply"] = reply
    if source is not None:
        entry["source"] = source
    if record_count is not None:
        entry["record_count"] = record_count
    if error is not None:
        entry["error"] = error

    log_path = config.CHAT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    filelogger.logger.info(f"Chat logged: {question[:120]!r} -> {source or error or 'pending'}")
