import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
import deepseek
import filelogger
import main as pipeline
from summary import build_summary, filter_rows

app = FastAPI(title="Tree Complaint Analyst")

_chat_history: list[dict[str, str]] = []
_cached_rows: list[dict[str, Any]] | None = None
_cached_summary: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str


def _load_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _cached_rows, _cached_summary

    if _cached_rows is not None and _cached_summary is not None:
        return _cached_rows, _cached_summary

    if not config.DATA_PATH.exists():
        raise FileNotFoundError("data.json not found. Run the pipeline first.")

    rows = json.loads(config.DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("data.json must contain a JSON array")

    _cached_rows = rows
    _cached_summary = build_summary(rows)
    return rows, _cached_summary


def _invalidate_cache() -> None:
    global _cached_rows, _cached_summary, _chat_history
    _cached_rows = None
    _cached_summary = None
    _chat_history = []


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    if config.REPORT_PATH.exists():
        return HTMLResponse(config.REPORT_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(
        "<h1>No report yet</h1><p>Run <code>python -m main</code> from the project root.</p>",
        status_code=404,
    )


@app.get("/api/summary")
def get_summary() -> dict[str, Any]:
    try:
        _, summary = _load_dataset()
        return summary
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, str]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        rows, summary = _load_dataset()
        sample_rows = filter_rows(rows, message, limit=8)
        messages = deepseek.build_chat_messages(
            summary, _chat_history, message, sample_rows
        )
        reply = deepseek.chat_completion(messages, max_tokens=512)
        _chat_history.append({"role": "user", "content": message})
        _chat_history.append({"role": "assistant", "content": reply})
        return {"reply": reply}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        filelogger.logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/refresh")
def refresh() -> dict[str, str]:
    _invalidate_cache()
    if not pipeline.run_pipeline():
        raise HTTPException(status_code=500, detail="Pipeline failed. Check logs.")
    return {"status": "ok", "message": "Data refreshed and report regenerated"}


@app.get("/report.html")
def report_file() -> FileResponse:
    if not config.REPORT_PATH.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(config.REPORT_PATH)
