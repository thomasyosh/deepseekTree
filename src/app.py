import json
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
import deepseek
import filelogger
import main as pipeline
from query_engine import try_answer_locally
from summary import build_summary
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Tree Complaint Analyst")


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



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

        local_reply = try_answer_locally(message, rows, summary)
        if local_reply:
            _chat_history.append({"role": "user", "content": message})
            _chat_history.append({"role": "assistant", "content": local_reply})
            return {"reply": local_reply, "source": "local"}

        messages = deepseek.build_chat_messages(
            summary, _chat_history, message, rows=rows
        )
        try:
            reply = deepseek.chat_completion(
                messages,
                model=config.CHAT_MODEL,
                max_tokens=config.CHAT_MAX_TOKENS,
                timeout=config.CHAT_TIMEOUT,
            )
            source = "ai"
        except requests.exceptions.Timeout:
            filelogger.logger.error(
                f"Chat timed out after {config.CHAT_TIMEOUT}s "
                f"(model={config.CHAT_MODEL})"
            )
            reply = (
                "<p><strong>AI timed out.</strong> Try a faster model:</p>"
                "<pre>ollama pull deepseek-r1:7b</pre>"
                "<p>Then set <code>CHAT_MODEL=deepseek-r1:7b</code> in .env "
                "and restart the server.</p>"
                "<p>For ranking questions (e.g. top 5 serious areas), "
                "answers are returned instantly without AI.</p>"
            )
            source = "timeout"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            filelogger.logger.error(f"Chat request failed: {e}")
            if status == 403:
                reply = (
                    "<p><strong>Ollama returned 403 Forbidden.</strong></p>"
                    "<p>On company networks this usually means the request was "
                    "sent through the corporate proxy instead of directly to "
                    "Ollama on your machine.</p>"
                    "<p>Ensure Ollama is running, set "
                    "<code>OLLAMA_URL=http://127.0.0.1:11434/v1/chat/completions</code> "
                    "in .env, restart the server, and test:</p>"
                    "<pre>curl.exe http://127.0.0.1:11434/api/tags</pre>"
                    f"<p><em>{e}</em></p>"
                )
            else:
                reply = (
                    f"<p><strong>Could not reach Ollama.</strong> "
                    f"Ensure it is running on port 11434.</p>"
                    f"<p><em>{e}</em></p>"
                )
            source = "error"
        except requests.exceptions.RequestException as e:
            filelogger.logger.error(f"Chat request failed: {e}")
            reply = (
                f"<p><strong>Could not reach Ollama.</strong> "
                f"Ensure it is running on port 11434.</p>"
                f"<p><em>{e}</em></p>"
            )
            source = "error"

        _chat_history.append({"role": "user", "content": message})
        _chat_history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "source": source}
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
