import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field

import config
import chat_log
import chat_export
import deepseek
import filelogger
import llm_client
import main as pipeline
from query_engine import try_answer_locally
from summary import build_summary
from fastapi.middleware.cors import CORSMiddleware
from chat_normalize import is_export_request
from prompts import build_export_ready_html
from report_builder import build_report_html, read_stored_narrative

@asynccontextmanager
async def lifespan(app: FastAPI):
    filelogger.logger.info(
        f"Startup: LLM_PROVIDER={config.LLM_PROVIDER}, ensuring dataset is available"
    )
    pipeline.ensure_dataset(generate_report=True)

    health = llm_client.check_llm_health()
    if health["ok"]:
        filelogger.logger.info(
            f"Ollama OK @ {config.OLLAMA_BASE_URL} "
            f"(models: {', '.join(health.get('models_available', [])) or 'none'}, "
            f"chat_timeout={config.CHAT_TIMEOUT}s)"
        )
        for hint in health.get("hints", []):
            filelogger.logger.warning(f"LLM: {hint}")
        if config.OLLAMA_WARMUP:
            llm_client.warm_up_model()
    else:
        filelogger.logger.error(
            f"LLM NOT ready ({config.LLM_PROVIDER}): {health.get('error')}"
        )
        for hint in health.get("hints", []):
            filelogger.logger.error(f"  → {hint}")
        filelogger.logger.error(
            "  → Ensure Ollama is running: ollama pull deepseek-r1:14b"
        )
        filelogger.logger.error("  → Diagnostics: http://127.0.0.1:8000/api/llm-health")

    yield


app = FastAPI(title="Tree Complaint Analyst", lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



_chat_history: list[dict[str, str]] = []
_cached_rows: list[dict[str, Any]] | None = None
_cached_summary: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    message: str
    refresh_data: bool | None = None


class ChatExportMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    role: str
    text: str
    is_html: bool = Field(False, alias="isHtml")


class ChatExportRequest(BaseModel):
    messages: list[ChatExportMessage]
    title: str | None = None


def _refresh_dataset_or_raise() -> None:
    if not pipeline.refresh_dataset(generate_report=False):
        raise HTTPException(
            status_code=503,
            detail="Could not refresh data from ENDPOINT. Check ENDPOINT, API_KEY, and logs.",
        )
    _invalidate_data_cache()


def _chat_response(
    *,
    reply: str,
    source: str,
    message: str,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    data_refreshed: bool,
    trigger_download: bool = False,
) -> dict[str, Any]:
    return {
        "reply": reply,
        "source": source,
        "question": message,
        "data_refreshed": data_refreshed,
        "record_count": summary.get("total_cases", len(rows)),
        "summary": summary,
        "trigger_download": trigger_download,
        "report_url": "/report.html" if config.REPORT_PATH.exists() else None,
    }


def _load_dataset() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    global _cached_rows, _cached_summary

    if _cached_rows is not None and _cached_summary is not None:
        return _cached_rows, _cached_summary

    if not config.DATA_PATH.exists() or not pipeline.dataset_is_ready():
        if not pipeline.ensure_dataset(generate_report=False):
            raise FileNotFoundError(
                "data.json not found. Set ENDPOINT in .env or POST /api/refresh."
            )

    rows = json.loads(config.DATA_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("data.json must contain a JSON array")

    _cached_rows = rows
    _cached_summary = build_summary(rows)
    return rows, _cached_summary


def _invalidate_data_cache() -> None:
    global _cached_rows, _cached_summary
    _cached_rows = None
    _cached_summary = None


def _invalidate_cache() -> None:
    global _chat_history
    _invalidate_data_cache()
    _chat_history = []


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Always build the page from the latest UI template (avoids stale report.html)."""
    headers = {"Cache-Control": "no-store"}
    try:
        rows, summary = _load_dataset()
        narrative = read_stored_narrative(config.REPORT_PATH)
        html = build_report_html(summary, narrative, rows=rows)
        return HTMLResponse(html, headers=headers)
    except (FileNotFoundError, ValueError):
        if config.REPORT_PATH.exists():
            return HTMLResponse(
                config.REPORT_PATH.read_text(encoding="utf-8"),
                headers=headers,
            )
    return HTMLResponse(
        "<h1>No report yet</h1>"
        "<p>Data is loading or report generation is still in progress.</p>"
        f"<p>Expected file: <code>{config.REPORT_PATH.resolve()}</code></p>"
        "<p>Try <code>POST /api/refresh</code> or send a chat message to regenerate.</p>",
        status_code=404,
    )


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/llm-health")
def llm_health() -> dict[str, Any]:
    """LLM diagnostics (OpenAI or Ollama depending on LLM_PROVIDER)."""
    return llm_client.check_llm_health()


@app.get("/api/ollama-health")
def ollama_health() -> dict[str, Any]:
    """Ollama-only diagnostics (legacy endpoint)."""
    return deepseek.check_ollama_health()


@app.get("/api/config")
def api_config() -> dict[str, Any]:
    return {
        "api_base_url": config.API_BASE_URL,
        "chat_timeout_seconds": config.CHAT_TIMEOUT,
        "chat_model": config.CHAT_MODEL,
        "ollama_base_url": config.OLLAMA_BASE_URL,
    }


@app.get("/api/summary")
def get_summary() -> dict[str, Any]:
    try:
        _, summary = _load_dataset()
        return summary
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/data/refresh")
def refresh_data_only() -> dict[str, Any]:
    """Fetch fresh data.json from Supabase (fast). Used before chat to update the report pane."""
    if not config.ENDPOINT:
        raise HTTPException(
            status_code=503,
            detail="ENDPOINT is not set in .env — cannot refresh data.",
        )
    try:
        _refresh_dataset_or_raise()
        rows, summary = _load_dataset()
        return {
            "ok": True,
            "record_count": len(rows),
            "summary": summary,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    should_refresh = (
        request.refresh_data
        if request.refresh_data is not None
        else config.REFRESH_DATA_ON_CHAT
    )

    try:
        if should_refresh:
            if not pipeline.refresh_dataset(generate_report=False):
                chat_log.log_chat(message, error="data refresh failed")
                raise HTTPException(
                    status_code=503,
                    detail="Could not refresh data from ENDPOINT. Check ENDPOINT, API_KEY, and logs.",
                )
            _invalidate_data_cache()

        rows, summary = _load_dataset()

        if is_export_request(message):
            _chat_history.append({"role": "user", "content": message})
            reply = build_export_ready_html()
            _chat_history.append({"role": "assistant", "content": reply})
            chat_log.log_chat(message, reply=reply, source="export", record_count=len(rows))
            return _chat_response(
                reply=reply,
                source="export",
                message=message,
                rows=rows,
                summary=summary,
                data_refreshed=should_refresh,
                trigger_download=True,
            )

        local_reply, filtered_summary = try_answer_locally(message, rows, summary)
        if local_reply:
            _chat_history.append({"role": "user", "content": message})
            _chat_history.append({"role": "assistant", "content": local_reply})
            chat_log.log_chat(
                message,
                reply=local_reply,
                source="local",
                record_count=len(rows),
            )
            return _chat_response(
                reply=local_reply,
                source="local",
                message=message,
                rows=rows,
                summary=filtered_summary or summary,
                data_refreshed=should_refresh,
            )

        messages = deepseek.build_chat_messages(
            summary, _chat_history, message, rows=rows
        )
        try:
            reply = llm_client.chat_completion(
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
                "<p><strong>AI timed out.</strong></p>"
                f"<p>Waited {config.CHAT_TIMEOUT}s for <code>{config.CHAT_MODEL}</code> "
                "on CPU — this is common on company laptops.</p>"
                "<ul>"
                "<li>Set <code>CHAT_TIMEOUT=600</code> in .env and restart</li>"
                "<li>Use <code>deepseek-r1:7b</code> instead of 14b</li>"
                "<li>First request loads the model — check server logs for warm-up</li>"
                "</ul>"
                "<p>For ranking questions (e.g. top 5 serious areas), "
                "answers are returned instantly without AI.</p>"
            )
            source = "timeout"
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            filelogger.logger.error(f"Chat request failed: {e}")
            if config.LLM_PROVIDER == "ollama" and status == 403:
                reply = (
                    "<p><strong>Ollama returned 403 Forbidden.</strong></p>"
                    "<p>Check Ollama is running and "
                    "<code>OLLAMA_OPENAI_BASE_URL=http://127.0.0.1:11434/v1</code> "
                    "in .env.</p>"
                    f"<p><em>{e}</em></p>"
                )
            elif config.LLM_PROVIDER == "ollama" and status == 500 and "killed" in str(e).lower():
                reply = (
                    "<p><strong>Ollama ran out of memory.</strong></p>"
                    "<p>Use <code>deepseek-r1:7b</code> and "
                    "<code>OLLAMA_NUM_CTX=2048</code> in .env.</p>"
                    f"<p><em>{e}</em></p>"
                )
            else:
                reply = llm_client.llm_troubleshooting_html(e)
            source = "error"
        except requests.exceptions.RequestException as e:
            filelogger.logger.error(f"Chat request failed: {e}")
            reply = llm_client.llm_troubleshooting_html(e)
            source = "error"
        except Exception as e:
            filelogger.logger.error(f"Chat request failed: {e}")
            reply = llm_client.llm_troubleshooting_html(e)
            source = "error"

        _chat_history.append({"role": "user", "content": message})
        _chat_history.append({"role": "assistant", "content": reply})
        chat_log.log_chat(
            message,
            reply=reply,
            source=source,
            record_count=len(rows),
        )
        return _chat_response(
            reply=reply,
            source=source,
            message=message,
            rows=rows,
            summary=summary,
            data_refreshed=should_refresh,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        filelogger.logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/chat/reset")
def reset_chat_session() -> dict[str, str]:
    """Clear server-side LLM conversation context for a fresh chat."""
    global _chat_history
    _chat_history = []
    return {"status": "ok"}


@app.post("/api/chat/export")
def export_chat_report(request: ChatExportRequest) -> Response:
    """Build a downloadable HTML report from the user's chat session."""
    if not any(m.role == "user" for m in request.messages):
        raise HTTPException(
            status_code=400,
            detail="No user messages to export. Ask at least one question first.",
        )

    try:
        _, summary = _load_dataset()
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    payload = [
        {"role": m.role, "text": m.text, "isHtml": m.is_html}
        for m in request.messages
    ]
    html_content = chat_export.build_chat_export_html(
        payload,
        summary,
        title=request.title or "Tree Complaint Analysis — Chat Report",
    )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"tree-chat-report-{stamp}.html"
    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/refresh")
def refresh() -> dict[str, str]:
    _invalidate_cache()
    if not pipeline.refresh_dataset(generate_report=True):
        raise HTTPException(status_code=500, detail="Pipeline failed. Check logs.")
    return {
        "status": "ok",
        "message": "Data refreshed and report regenerated",
        "data_path": str(config.DATA_PATH.resolve()),
        "report_path": str(config.REPORT_PATH.resolve()),
        "report_url": "/report.html",
    }


@app.get("/report.html")
def report_file() -> FileResponse:
    if not config.REPORT_PATH.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(config.REPORT_PATH)
