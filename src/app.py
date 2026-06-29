import json
from contextlib import asynccontextmanager
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import config
import deepseek
import filelogger
import llm_client
import main as pipeline
from query_engine import try_answer_locally
from summary import build_summary
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    filelogger.logger.info(
        f"Startup: LLM_PROVIDER={config.LLM_PROVIDER}, ensuring dataset is available"
    )
    pipeline.ensure_dataset(generate_report=True)

    health = llm_client.check_llm_health()
    if health["ok"]:
        if config.LLM_PROVIDER == "ollama":
            filelogger.logger.info(
                f"Local DeepSeek OK via OpenAI API @ {config.OLLAMA_OPENAI_BASE_URL} "
                f"(models: {', '.join(health.get('models_available', [])) or 'none'})"
            )
        for hint in health.get("hints", []):
            filelogger.logger.warning(f"LLM: {hint}")
    else:
        filelogger.logger.error(
            f"LLM NOT ready ({config.LLM_PROVIDER}): {health.get('error')}"
        )
        for hint in health.get("hints", []):
            filelogger.logger.error(f"  → {hint}")
        if config.LLM_PROVIDER == "cloud":
            filelogger.logger.error(
                "  → Or set LLM_PROVIDER=ollama for local DeepSeek via Ollama"
            )
        else:
            filelogger.logger.error(
                "  → Ensure Ollama is running and deepseek-r1:7b is pulled"
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
        "<h1>No report yet</h1>"
        "<p>Data is loading or report generation is still in progress. "
        "Try <code>POST /api/refresh</code> or check server logs.</p>",
        status_code=404,
    )


@app.get("/api/llm-health")
def llm_health() -> dict[str, Any]:
    """LLM diagnostics (OpenAI or Ollama depending on LLM_PROVIDER)."""
    return llm_client.check_llm_health()


@app.get("/api/ollama-health")
def ollama_health() -> dict[str, Any]:
    """Ollama-only diagnostics (legacy endpoint)."""
    return deepseek.check_ollama_health()


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
                "<p><strong>AI timed out.</strong> Try a faster model "
                f"(current: <code>{config.CHAT_MODEL}</code>).</p>"
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
