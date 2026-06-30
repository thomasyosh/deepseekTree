import html
import json
import re
from pathlib import Path
from typing import Any

import config
from prompts import CHAT_EXAMPLE_QUESTIONS, build_chat_welcome_html
from testing_guide import build_testing_guide_html

TABLE_SECTIONS: list[tuple[str, str]] = [
    ("by_district", "Cases by District"),
    ("by_status", "Cases by Status"),
    ("by_severity", "Cases by Severity"),
    ("by_complaint_type", "Cases by Complaint Type"),
    ("by_contractor", "Cases by Contractor"),
]

_DEFAULT_NARRATIVE = "<p><em>AI analysis will appear here after report generation.</em></p>"


def read_stored_narrative(report_path: Path | None = None) -> str:
    """Extract the narrative block from an existing report.html, if present."""
    path = report_path or config.REPORT_PATH
    if not path.exists():
        return _DEFAULT_NARRATIVE
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r'id="report-narrative"[^>]*>\s*<h2>AI Analysis</h2>\s*(.*?)\s*</section>',
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return _DEFAULT_NARRATIVE
    body = match.group(1).strip()
    return body or _DEFAULT_NARRATIVE


def _table(title: str, data: dict[str, int]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>"
        for k, v in sorted(data.items(), key=lambda item: item[1], reverse=True)
    )
    return f"""
    <section class="card">
      <h2>{html.escape(title)}</h2>
      <table>
        <thead><tr><th>Category</th><th>Count</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    """


def build_report_html(
    summary: dict[str, Any],
    narrative: str,
    rows: list[dict[str, Any]] | None = None,
) -> str:
    overview = f"""
    <section class="card">
      <h2>Overview</h2>
      <ul>
        <li><strong>Total cases:</strong> {summary.get("total_cases", 0)}</li>
        <li><strong>Total trees:</strong> {summary.get("total_trees", 0)}</li>
        <li><strong>Date range:</strong> {summary.get("date_range", ["—", "—"])[0]} → {summary.get("date_range", ["—", "—"])[1]}</li>
      </ul>
    </section>
    """

    tables = "".join(
        _table(title, summary[key])
        for key, title in TABLE_SECTIONS
        if key in summary
    )

    safe_narrative = narrative.strip() or "<p>No narrative generated.</p>"
    testing_guide = build_testing_guide_html(summary, rows)
    api_base = html.escape(config.API_BASE_URL)
    table_sections_json = html.escape(
        json.dumps([{"key": k, "title": t} for k, t in TABLE_SECTIONS]),
        quote=True,
    )
    chat_welcome_json = json.dumps(build_chat_welcome_html(), ensure_ascii=False)
    chat_placeholder = html.escape(CHAT_EXAMPLE_QUESTIONS[0])

    return f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="chat-timeout-seconds" content="{config.CHAT_TIMEOUT}" />
  <meta name="api-base-url" content="{api_base}" />
  <meta name="report-table-sections" content="{table_sections_json}" />
  <title>Tree Complaint Analysis Report</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --card: #ffffff;
      --text: #1a1a2e;
      --muted: #5c6370;
      --accent: #2563eb;
      --border: #e5e7eb;
      --sidebar-width: 380px;
      --chat-pane-height: 42vh;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ height: 100%; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      overflow: hidden;
    }}
    .layout {{
      display: flex;
      flex-direction: row;
      height: 100vh;
      height: 100dvh;
      width: 100%;
      overflow: hidden;
    }}
    .main {{
      flex: 1 1 auto;
      min-width: 240px;
      padding: 1.25rem 1.5rem 2rem;
      overflow-y: auto;
      overflow-x: hidden;
      -webkit-overflow-scrolling: touch;
    }}
    .pane-resizer {{
      flex: 0 0 7px;
      cursor: col-resize;
      background: linear-gradient(90deg, transparent, var(--border) 35%, var(--border) 65%, transparent);
      touch-action: none;
      position: relative;
      z-index: 2;
    }}
    .pane-resizer::after {{
      content: "";
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 3px;
      height: 2.5rem;
      border-radius: 3px;
      background: #cbd5e1;
    }}
    .pane-resizer:hover,
    .pane-resizer:focus-visible {{
      background: #dbeafe;
      outline: none;
    }}
    .layout.is-resizing {{
      cursor: col-resize;
      user-select: none;
    }}
    .layout.is-resizing .main,
    .layout.is-resizing .sidebar {{
      pointer-events: none;
    }}
    .sidebar {{
      flex: 0 0 var(--sidebar-width);
      width: var(--sidebar-width);
      min-width: 260px;
      max-width: min(75vw, 900px);
      background: var(--card);
      border-left: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      min-height: 0;
      overflow: hidden;
    }}
    h1 {{ margin-top: 0; font-size: clamp(1.35rem, 2.5vw, 1.75rem); }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem;
      margin-bottom: 1rem;
      overflow-x: auto;
    }}
    table {{ width: 100%; border-collapse: collapse; min-width: 260px; }}
    th, td {{
      text-align: left;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--border);
    }}
    .narrative {{ line-height: 1.6; }}
    .chat-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }}
    .chat-title {{
      font-weight: 600;
      font-size: 0.95rem;
      line-height: 1.3;
    }}
    .chat-toolbar {{
      display: flex;
      gap: 0.35rem;
      flex-shrink: 0;
    }}
    .chat-toolbar button,
    .chat-actions button {{
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fff;
      color: var(--text);
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      padding: 0.4rem 0.65rem;
      white-space: nowrap;
    }}
    .chat-toolbar button:hover,
    .chat-actions button:hover {{ background: #f9fafb; }}
    .chat-toolbar button:disabled,
    .chat-actions button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .chat-toolbar button.primary {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}
    .chat-messages {{
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      padding: 1rem 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
      -webkit-overflow-scrolling: touch;
    }}
    .msg {{
      padding: 0.75rem 1rem;
      border-radius: 10px;
      max-width: 95%;
      line-height: 1.5;
      white-space: pre-wrap;
    }}
    .msg.user {{ background: #dbeafe; align-self: flex-end; }}
    .msg.assistant {{ background: #f3f4f6; align-self: flex-start; }}
    .msg-label {{
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--muted);
      margin-bottom: 0.25rem;
    }}
    .chat-input {{
      display: flex;
      gap: 0.5rem;
      padding: 0.75rem 1rem;
      border-top: 1px solid var(--border);
      flex-shrink: 0;
    }}
    .chat-input input {{
      flex: 1;
      padding: 0.75rem 1rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.95rem;
    }}
    .chat-input button {{
      background: var(--accent);
      color: white;
      border: none;
      border-radius: 8px;
      padding: 0 1rem;
      cursor: pointer;
      font-weight: 600;
    }}
    .chat-input button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
    .chat-actions {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      padding: 0 1rem 1rem;
      flex-shrink: 0;
    }}
    .chat-actions button {{
      width: 100%;
      padding: 0.65rem 1rem;
      font-size: 0.9rem;
    }}
    .chat-actions button.download-btn {{
      background: #fff;
    }}
    .chat-input button.loading::after {{
      content: "…";
      animation: dots 1.2s steps(4, end) infinite;
    }}
    @keyframes dots {{
      0%, 20% {{ content: ""; }}
      40% {{ content: "."; }}
      60% {{ content: ".."; }}
      80%, 100% {{ content: "..."; }}
    }}
    .chat-status {{
      padding: 0.5rem 1rem;
      font-size: 0.85rem;
      color: var(--muted);
      min-height: 1.25rem;
    }}
    .chat-status.busy {{
      color: var(--accent);
      font-weight: 500;
    }}
    .msg.thinking {{
      animation: pulse-thinking 1.5s ease-in-out infinite;
    }}
    @keyframes pulse-thinking {{
      0%, 100% {{ opacity: 0.55; }}
      50% {{ opacity: 1; }}
    }}
    .file-warning {{
      background: #fef3c7;
      color: #92400e;
      padding: 0.75rem 1rem;
      margin: 0 1rem 0.5rem;
      border-radius: 8px;
      font-size: 0.85rem;
      display: none;
    }}
    .file-warning a {{ color: #1d4ed8; }}
    .live-server-info {{
      background: #dbeafe;
      color: #1e3a8a;
      padding: 0.75rem 1rem;
      margin: 0 1rem 0.5rem;
      border-radius: 8px;
      font-size: 0.85rem;
      display: none;
    }}
    .live-server-info a {{ color: #1d4ed8; }}
    .conn-ok {{ color: #15803d; }}
    .conn-bad {{ color: #b91c1c; }}
    .data-updated {{
      font-size: 0.85rem;
      color: var(--muted);
      margin: -0.5rem 0 1rem;
      min-height: 1.25rem;
    }}
    .data-updated.flash {{
      color: #15803d;
      font-weight: 500;
    }}
    .main-updating {{
      opacity: 0.65;
      pointer-events: none;
      transition: opacity 0.2s;
    }}
    .test-guide {{
      border-color: #bfdbfe;
      background: linear-gradient(180deg, #f8fbff 0%, var(--card) 4rem);
    }}
    .test-guide-panel {{ border: none; }}
    .test-guide-summary {{
      cursor: pointer;
      list-style: none;
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      padding: 0.15rem 0;
    }}
    .test-guide-summary::-webkit-details-marker {{ display: none; }}
    .test-guide-summary::before {{
      content: "▸";
      float: left;
      margin-right: 0.5rem;
      color: var(--accent);
      transition: transform 0.15s;
    }}
    .test-guide-panel[open] .test-guide-summary::before {{
      transform: rotate(90deg);
    }}
    .test-guide-title {{
      font-size: 1.15rem;
      font-weight: 700;
      color: #1e3a8a;
    }}
    .test-guide-sub {{
      font-size: 0.85rem;
      color: var(--muted);
      margin-left: 1.25rem;
    }}
    .test-guide-body {{ margin-top: 1rem; }}
    .test-intro {{
      font-size: 0.92rem;
      line-height: 1.55;
      color: var(--muted);
      margin: 0 0 1rem;
    }}
    .test-badge {{
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 0.15rem 0.45rem;
      border-radius: 999px;
      vertical-align: middle;
    }}
    .test-badge-local {{
      background: #dcfce7;
      color: #166534;
    }}
    .test-badge-ai {{
      background: #ede9fe;
      color: #5b21b6;
    }}
    .test-stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 0.65rem;
      margin-bottom: 1rem;
    }}
    .test-stat {{
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.65rem 0.75rem;
    }}
    .test-stat-label {{
      display: block;
      font-size: 0.75rem;
      color: var(--muted);
      margin-bottom: 0.2rem;
    }}
    .test-stat-value {{
      font-size: 0.95rem;
      font-weight: 600;
      word-break: break-word;
    }}
    .test-toolbar {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin-bottom: 0.75rem;
      flex-wrap: wrap;
    }}
    .test-filter-label {{
      font-size: 0.85rem;
      font-weight: 600;
      color: var(--muted);
    }}
    .test-filter {{
      padding: 0.4rem 0.65rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.9rem;
      background: #fff;
      min-width: 12rem;
    }}
    .test-cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 0.75rem;
    }}
    .test-card {{
      background: #fff;
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 0.85rem 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      min-width: 0;
    }}
    .test-card-head {{
      display: flex;
      align-items: center;
      gap: 0.4rem;
      flex-wrap: wrap;
    }}
    .test-card-num {{
      font-weight: 700;
      color: var(--accent);
      font-size: 0.85rem;
    }}
    .test-card-group {{
      font-size: 0.75rem;
      color: var(--muted);
      flex: 1;
    }}
    .test-question {{
      margin: 0;
      font-size: 0.92rem;
      line-height: 1.45;
      font-weight: 500;
    }}
    .test-try-btn {{
      align-self: flex-start;
      padding: 0.4rem 0.75rem;
      font-size: 0.8rem;
      font-weight: 600;
      border: 1px solid var(--accent);
      background: #eff6ff;
      color: var(--accent);
      border-radius: 8px;
      cursor: pointer;
    }}
    .test-try-btn:hover {{ background: #dbeafe; }}
    .test-answer-details {{
      font-size: 0.82rem;
      color: var(--muted);
      line-height: 1.5;
    }}
    .test-answer-details summary {{
      cursor: pointer;
      font-weight: 600;
      color: var(--text);
    }}
    .test-expected, .test-checks, .test-route-hint {{ margin: 0.5rem 0 0; }}
    .test-footnote {{
      margin: 1rem 0 0;
      font-size: 0.8rem;
      color: var(--muted);
      line-height: 1.45;
    }}
    .test-card.is-hidden {{ display: none; }}
    @media (max-width: 900px) {{
      body {{ overflow: auto; }}
      .layout {{
        flex-direction: column;
        height: auto;
        min-height: 100vh;
        min-height: 100dvh;
      }}
      .main {{
        flex: none;
        width: 100%;
        min-height: 50vh;
        max-height: none;
        padding: 1rem;
      }}
      .pane-resizer {{
        flex: 0 0 10px;
        width: 100%;
        cursor: row-resize;
        border-top: 1px solid var(--border);
        border-bottom: 1px solid var(--border);
      }}
      .pane-resizer::after {{
        width: 2.5rem;
        height: 3px;
      }}
      .layout.is-resizing {{
        cursor: row-resize;
      }}
      .sidebar {{
        flex: 0 0 var(--chat-pane-height);
        width: 100%;
        max-width: none;
        min-width: 0;
        min-height: 220px;
        max-height: 85vh;
        border-left: none;
      }}
      .chat-input input {{ font-size: 16px; }}
      .msg {{ max-width: 100%; }}
      .test-cards-grid {{ grid-template-columns: 1fr; }}
      .test-stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (max-width: 480px) {{
      .chat-header {{
        flex-wrap: wrap;
      }}
      .chat-toolbar {{
        width: 100%;
        justify-content: flex-end;
      }}
      .chat-input {{
        flex-wrap: wrap;
      }}
      .chat-input button {{
        width: 100%;
        padding: 0.75rem;
      }}
      .test-stats-grid {{ grid-template-columns: 1fr; }}
      .test-filter {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <div class="layout" id="app-layout">
    <main class="main" id="report-main">
      <h1>Tree Complaint Analysis Report</h1>
      <p id="report-data-updated" class="data-updated" aria-live="polite"></p>
      <div id="report-overview">{overview}</div>
      {testing_guide}
      <div id="report-tables">{tables}</div>
      <section class="card narrative" id="report-narrative">
        <h2>AI Analysis</h2>
        {safe_narrative}
      </section>
    </main>
    <div
      class="pane-resizer"
      id="pane-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label="Drag to resize report and chat panels"
      tabindex="0"
    ></div>
    <aside class="sidebar" id="chat-sidebar">
      <div class="chat-header">
        <span class="chat-title">Chat with AI Analyst</span>
        <div class="chat-toolbar">
          <button type="button" id="chat-new-session" title="Start a new chat session">New</button>
          <button type="button" id="chat-clear" title="Clear messages in this session">Clear</button>
        </div>
      </div>
      <div id="file-warning" class="file-warning"></div>
      <div id="live-server-info" class="live-server-info"></div>
      <div id="chat-status" class="chat-status"></div>
      <div id="chat-messages" class="chat-messages"></div>
      <form id="chat-form" class="chat-input">
        <input id="chat-input" type="text" placeholder="{chat_placeholder}" autocomplete="off" />
        <button type="submit" id="chat-send">Send</button>
      </form>
      <div class="chat-actions">
        <button type="button" class="download-btn" id="chat-download" title="Download this chat as HTML">
          Download chat report
        </button>
      </div>
    </aside>
  </div>
  <script type="application/json" id="chat-welcome-data">{chat_welcome_json}</script>
  <script>
    const configuredApiBase = document.querySelector('meta[name="api-base-url"]')?.content
      || "{api_base}";
    const chatTimeoutSec = parseInt(
      document.querySelector('meta[name="chat-timeout-seconds"]')?.content || "300",
      10
    );
    const clientTimeoutMs = (chatTimeoutSec + 120) * 1000;
    const isFilePage = window.location.protocol === "file:";
    const apiBase = configuredApiBase.replace(/\\/$/, "");

    function isFastApiOrigin() {{
      if (isFilePage) return false;
      const host = window.location.hostname;
      const local = host === "127.0.0.1" || host === "localhost" || host === "[::1]";
      return local && window.location.port === "8000";
    }}

    function isCrossOriginPreview() {{
      return !isFilePage && !isFastApiOrigin();
    }}

    /** FastAPI on :8000 → same-origin /api/... ; Live Server etc. → full URL to uvicorn. */
    function apiUrl(path) {{
      if (isFilePage) return null;
      if (isFastApiOrigin()) return path;
      return apiBase + path;
    }}

    function chatEndpoint() {{
      return apiUrl("/api/chat");
    }}

    const statusEl = document.getElementById("chat-status");
    const fileWarning = document.getElementById("file-warning");
    const liveServerInfo = document.getElementById("live-server-info");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("chat-send");
    const downloadBtn = document.getElementById("chat-download");
    const clearBtn = document.getElementById("chat-clear");
    const newSessionBtn = document.getElementById("chat-new-session");
    const messages = document.getElementById("chat-messages");
    const appLayout = document.getElementById("app-layout");
    const paneResizer = document.getElementById("pane-resizer");
    const chatSidebar = document.getElementById("chat-sidebar");

    function setStatus(text, busy) {{
      statusEl.textContent = text || "";
      statusEl.classList.toggle("busy", !!busy);
    }}

    if (isFilePage) {{
      fileWarning.style.display = "block";
      fileWarning.innerHTML =
        "<strong>Chat disabled:</strong> this page was opened as a local file " +
        "(<code>file://</code>). Browsers block that from calling the API. " +
        "Open " +
        '<a href="' + apiBase + '/" target="_blank" rel="noopener">' +
        apiBase + "/</a> instead (keep the server running).";
    }} else if (isCrossOriginPreview()) {{
      liveServerInfo.style.display = "block";
      liveServerInfo.innerHTML =
        "Preview server detected (<code>" + window.location.origin + "</code>). " +
        "Chat will call <strong>" + apiBase + "</strong> — keep uvicorn running there. " +
        'Simplest option: <a href="' + apiBase + '/">' + apiBase + "/</a>";
    }}

    async function checkApiConnection() {{
      if (isFilePage) {{
        setStatus("Not connected — open via " + apiBase + "/", false);
        return false;
      }}
      const healthUrl = apiUrl("/api/health");
      try {{
        const res = await fetch(healthUrl, {{
          method: "GET",
          credentials: isFastApiOrigin() ? "same-origin" : "omit",
          mode: "cors",
        }});
        if (!res.ok) throw new Error("HTTP " + res.status);
        setStatus("Connected to API at " + apiBase, false);
        statusEl.classList.add("conn-ok");
        return true;
      }} catch (err) {{
        setStatus(
          "Cannot reach API at " + apiBase +
          " — start uvicorn (port 8000), then reload this page.",
          false
        );
        statusEl.classList.add("conn-bad");
        console.error("API health check failed:", healthUrl, err);
        return false;
      }}
    }}

    const reportMain = document.getElementById("report-main");
    const reportOverview = document.getElementById("report-overview");
    const reportTables = document.getElementById("report-tables");
    const reportDataUpdated = document.getElementById("report-data-updated");
    const tableSections = JSON.parse(
      document.querySelector('meta[name="report-table-sections"]')?.content || "[]"
    );

    function escapeHtml(text) {{
      const el = document.createElement("span");
      el.textContent = text == null ? "" : String(text);
      return el.innerHTML;
    }}

    function buildOverviewHtml(summary) {{
      const dr = summary.date_range || ["—", "—"];
      return (
        '<section class="card">' +
        "<h2>Overview</h2><ul>" +
        "<li><strong>Total cases:</strong> " + (summary.total_cases || 0) + "</li>" +
        "<li><strong>Total trees:</strong> " + (summary.total_trees || 0) + "</li>" +
        "<li><strong>Date range:</strong> " + escapeHtml(dr[0]) + " → " + escapeHtml(dr[1]) + "</li>" +
        "</ul></section>"
      );
    }}

    function buildTableHtml(title, data) {{
      const rows = Object.entries(data || {{}})
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => "<tr><td>" + escapeHtml(k) + "</td><td>" + v + "</td></tr>")
        .join("");
      return (
        '<section class="card"><h2>' + escapeHtml(title) + "</h2>" +
        "<table><thead><tr><th>Category</th><th>Count</th></tr></thead>" +
        "<tbody>" + rows + "</tbody></table></section>"
      );
    }}

    function updateReportPane(summary, recordCount) {{
      if (!summary || !reportOverview || !reportTables) return;
      reportOverview.innerHTML = buildOverviewHtml(summary);
      reportTables.innerHTML = tableSections
        .filter((s) => summary[s.key])
        .map((s) => buildTableHtml(s.title, summary[s.key]))
        .join("");
      if (reportDataUpdated) {{
        const n = recordCount != null ? recordCount : summary.total_cases || 0;
        reportDataUpdated.textContent =
          "Data updated · " + n + " records · " + new Date().toLocaleTimeString();
        reportDataUpdated.classList.add("flash");
        setTimeout(() => reportDataUpdated.classList.remove("flash"), 2500);
      }}
    }}

    async function loadLatestSummary() {{
      const url = apiUrl("/api/summary");
      if (!url) return;
      try {{
        const res = await fetch(url, {{
          method: "GET",
          credentials: isFastApiOrigin() ? "same-origin" : "omit",
          mode: "cors",
        }});
        if (!res.ok) return;
        const summary = await res.json();
        updateReportPane(summary, summary.total_cases);
      }} catch (err) {{
        console.warn("Could not load latest summary for report pane", err);
      }}
    }}

    if (!isFilePage) {{
      checkApiConnection().then((ok) => {{
        if (ok) loadLatestSummary();
      }});
    }}

    let thinkingEl = null;

    function showThinking() {{
      removeThinking();
      thinkingEl = document.createElement("div");
      thinkingEl.className = "msg assistant thinking";
      thinkingEl.id = "chat-thinking";
      thinkingEl.innerHTML =
        '<div class="msg-label">Assistant</div>' +
        '<div>Working on your question…</div>';
      messages.appendChild(thinkingEl);
      messages.scrollTop = messages.scrollHeight;
    }}

    function removeThinking() {{
      if (thinkingEl) {{
        thinkingEl.remove();
        thinkingEl = null;
      }}
    }}

    function formatFetchError(err) {{
      if (err.name === "AbortError") {{
        return (
          "Timed out in browser after " + Math.round(clientTimeoutMs / 1000) + "s. " +
          "Increase CHAT_TIMEOUT in .env or try a simpler question."
        );
      }}
      if (err.message === "Failed to fetch") {{
        if (isFilePage) {{
          return (
            "Failed to fetch — you opened report.html as a file. " +
            "Use " + apiBase + "/ in the browser (not double-click report.html)."
          );
        }}
        if (isCrossOriginPreview()) {{
          return (
            "Failed to fetch — could not reach " + apiBase + " from Live Server. " +
            "Ensure uvicorn is running on port 8000, or open " + apiBase + "/ directly."
          );
        }}
        return (
          "Failed to fetch — browser could not reach the API. " +
          "Use " + apiBase + "/ (not Live Server) if this keeps happening. " +
          "Also avoid --reload while chatting — server restarts drop in-flight requests."
        );
      }}
      return err.message || String(err);
    }}

    function formatErrorDetail(detail) {{
      if (!detail) return "Request failed";
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail);
    }}

    let chatInFlight = false;
    const dataRefreshTimeoutMs = 90000;

    function fetchOptions(method, body) {{
      const opts = {{
        method,
        credentials: isFastApiOrigin() ? "same-origin" : "omit",
        mode: "cors",
      }};
      if (body != null) {{
        opts.headers = {{ "Content-Type": "application/json" }};
        opts.body = JSON.stringify(body);
      }}
      return opts;
    }}

    function fetchWithTimeout(url, options, timeoutMs) {{
      return new Promise((resolve, reject) => {{
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        fetch(url, {{ ...options, signal: controller.signal }})
          .then(resolve)
          .catch(reject)
          .finally(() => clearTimeout(timer));
      }});
    }}

    async function parseJsonResponse(res) {{
      const raw = await res.text();
      let data;
      try {{
        data = JSON.parse(raw);
      }} catch {{
        throw new Error(
          "API returned non-JSON (status " + res.status + "). " +
          "Reload from " + (isFastApiOrigin() ? window.location.origin : apiBase) + "/"
        );
      }}
      if (!res.ok) throw new Error(formatErrorDetail(data.detail));
      return data;
    }}

    async function tryRefreshData() {{
      const url = apiUrl("/api/data/refresh");
      if (!url) return false;
      try {{
        const res = await fetchWithTimeout(
          url,
          fetchOptions("POST", {{}}),
          dataRefreshTimeoutMs
        );
        const data = await parseJsonResponse(res);
        if (data.summary) updateReportPane(data.summary, data.record_count);
        return true;
      }} catch (err) {{
        console.warn("Data refresh failed; continuing with cached data", err);
        return false;
      }}
    }}

    async function postChat(text, allowRetry) {{
      const endpoint = chatEndpoint();
      try {{
        const res = await fetchWithTimeout(
          endpoint,
          fetchOptions("POST", {{ message: text, refresh_data: false }}),
          clientTimeoutMs
        );
        return parseJsonResponse(res);
      }} catch (err) {{
        if (allowRetry && err.message === "Failed to fetch") {{
          setStatus("Connection dropped — retrying once...", true);
          await new Promise((resolve) => setTimeout(resolve, 2000));
          return postChat(text, false);
        }}
        throw err;
      }}
    }}

    const SESSION_STORAGE_KEY = "deepseektree_session_id";
    const SIDEBAR_WIDTH_KEY = "deepseektree_sidebar_width";
    const CHAT_HEIGHT_KEY = "deepseektree_chat_height";
    const LEGACY_CHAT_KEY = "deepseektree_chat_history";

    function getSessionId() {{
      let id = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (!id) {{
        id = String(Date.now());
        sessionStorage.setItem(SESSION_STORAGE_KEY, id);
      }}
      return id;
    }}

    function chatStorageKey() {{
      return "deepseektree_chat_" + getSessionId();
    }}

    function migrateLegacyChat() {{
      try {{
        const legacy = sessionStorage.getItem(LEGACY_CHAT_KEY);
        if (!legacy) return;
        const key = chatStorageKey();
        if (!sessionStorage.getItem(key)) {{
          sessionStorage.setItem(key, legacy);
        }}
        sessionStorage.removeItem(LEGACY_CHAT_KEY);
      }} catch (err) {{
        console.warn("Could not migrate legacy chat storage", err);
      }}
    }}

    migrateLegacyChat();

    function loadStoredMessages() {{
      try {{
        const raw = sessionStorage.getItem(chatStorageKey());
        return raw ? JSON.parse(raw) : [];
      }} catch {{
        return [];
      }}
    }}

    function saveStoredMessages(items) {{
      try {{
        sessionStorage.setItem(chatStorageKey(), JSON.stringify(items));
      }} catch (err) {{
        console.warn("Could not save chat history", err);
      }}
    }}

    function isStackedLayout() {{
      return window.matchMedia("(max-width: 900px)").matches;
    }}

    function clampSidebarWidth(px) {{
      const min = 260;
      const max = Math.min(Math.floor(window.innerWidth * 0.75), window.innerWidth - 280);
      return Math.max(min, Math.min(px, Math.max(min, max)));
    }}

    function clampChatHeight(px) {{
      const min = 220;
      const max = Math.min(Math.floor(window.innerHeight * 0.85), window.innerHeight - 200);
      return Math.max(min, Math.min(px, Math.max(min, max)));
    }}

    function applySidebarWidth(px, persist) {{
      const w = clampSidebarWidth(px);
      document.documentElement.style.setProperty("--sidebar-width", w + "px");
      if (persist) localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w));
      return w;
    }}

    function applyChatHeight(px, persist) {{
      const h = clampChatHeight(px);
      document.documentElement.style.setProperty("--chat-pane-height", h + "px");
      if (persist) localStorage.setItem(CHAT_HEIGHT_KEY, String(h));
      return h;
    }}

    function loadPaneSizes() {{
      const savedWidth = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY) || "", 10);
      if (!Number.isNaN(savedWidth)) applySidebarWidth(savedWidth, false);
      const savedHeight = parseInt(localStorage.getItem(CHAT_HEIGHT_KEY) || "", 10);
      if (!Number.isNaN(savedHeight)) applyChatHeight(savedHeight, false);
    }}

    loadPaneSizes();

    let resizeMode = null;
    let resizeStart = 0;
    let resizeStartSize = 0;

    function onResizeMove(clientX, clientY) {{
      if (!resizeMode) return;
      if (resizeMode === "sidebar") {{
        const delta = resizeStart - clientX;
        applySidebarWidth(resizeStartSize + delta, true);
      }} else if (resizeMode === "chat-height") {{
        const delta = clientY - resizeStart;
        applyChatHeight(resizeStartSize + delta, true);
      }}
    }}

    function stopResize() {{
      resizeMode = null;
      appLayout?.classList.remove("is-resizing");
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", stopResize);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", stopResize);
    }}

    function onMouseMove(e) {{
      onResizeMove(e.clientX, e.clientY);
    }}

    function onTouchMove(e) {{
      if (!e.touches.length) return;
      e.preventDefault();
      onResizeMove(e.touches[0].clientX, e.touches[0].clientY);
    }}

    function startResize(e) {{
      if (e.type === "mousedown" && e.button !== 0) return;
      if (isStackedLayout()) {{
        resizeMode = "chat-height";
        resizeStart = e.touches ? e.touches[0].clientY : e.clientY;
        const h = parseInt(
          getComputedStyle(document.documentElement).getPropertyValue("--chat-pane-height"),
          10
        );
        resizeStartSize = Number.isNaN(h) ? chatSidebar.offsetHeight : h;
      }} else {{
        resizeMode = "sidebar";
        resizeStart = e.touches ? e.touches[0].clientX : e.clientX;
        resizeStartSize = chatSidebar.offsetWidth;
      }}
      appLayout?.classList.add("is-resizing");
      if (e.type === "touchstart") {{
        document.addEventListener("touchmove", onTouchMove, {{ passive: false }});
        document.addEventListener("touchend", stopResize);
      }} else {{
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", stopResize);
      }}
      e.preventDefault();
    }}

    paneResizer?.addEventListener("mousedown", startResize);
    paneResizer?.addEventListener("touchstart", startResize, {{ passive: false }});

    paneResizer?.addEventListener("keydown", (e) => {{
      const step = e.shiftKey ? 40 : 16;
      if (isStackedLayout()) {{
        const current = parseInt(
          getComputedStyle(document.documentElement).getPropertyValue("--chat-pane-height"),
          10
        ) || chatSidebar.offsetHeight;
        if (e.key === "ArrowUp") {{
          applyChatHeight(current - step, true);
          e.preventDefault();
        }} else if (e.key === "ArrowDown") {{
          applyChatHeight(current + step, true);
          e.preventDefault();
        }}
      }} else {{
        const current = chatSidebar.offsetWidth;
        if (e.key === "ArrowLeft") {{
          applySidebarWidth(current + step, true);
          e.preventDefault();
        }} else if (e.key === "ArrowRight") {{
          applySidebarWidth(current - step, true);
          e.preventDefault();
        }}
      }}
    }});

    window.addEventListener("resize", () => {{
      if (!isStackedLayout()) {{
        const w = chatSidebar.offsetWidth;
        applySidebarWidth(w, false);
      }} else {{
        const h = chatSidebar.offsetHeight;
        applyChatHeight(h, false);
      }}
    }});

    let storedMessages = loadStoredMessages();

    function showWelcomeMessage() {{
      const welcomeEl = document.getElementById("chat-welcome-data");
      const welcomeHtml = welcomeEl
        ? JSON.parse(welcomeEl.textContent || '""')
        : "Ask about districts, severity, dates, or totals in this dataset.";
      addMessage("assistant", welcomeHtml, true);
      storedMessages = loadStoredMessages();
    }}

    function renderStoredMessages() {{
      messages.innerHTML = "";
      storedMessages.forEach((item) => {{
        const el = document.createElement("div");
        el.className = "msg " + item.role;
        const label = document.createElement("div");
        label.className = "msg-label";
        label.textContent = item.role === "user" ? "You" : "Assistant";
        el.appendChild(label);
        const body = document.createElement("div");
        if (item.isHtml) {{
          body.innerHTML = item.text;
        }} else {{
          body.textContent = item.text;
        }}
        el.appendChild(body);
        messages.appendChild(el);
      }});
      messages.scrollTop = messages.scrollHeight;
    }}

    async function resetServerChat() {{
      const url = apiUrl("/api/chat/reset");
      if (!url) return;
      try {{
        await fetchWithTimeout(url, fetchOptions("POST", {{}}), 15000);
      }} catch (err) {{
        console.warn("Could not reset server chat context", err);
      }}
    }}

    function setChatControlsDisabled(disabled) {{
      if (clearBtn) clearBtn.disabled = disabled;
      if (newSessionBtn) newSessionBtn.disabled = disabled;
      if (downloadBtn) downloadBtn.disabled = disabled;
    }}

    async function clearChatSession() {{
      if (chatInFlight) return;
      if (storedMessages.length === 0) {{
        setStatus("Chat is already empty.", false);
        return;
      }}
      if (!window.confirm("Clear all messages in this chat session?")) return;

      setChatControlsDisabled(true);
      await resetServerChat();
      storedMessages = [];
      saveStoredMessages([]);
      messages.innerHTML = "";
      showWelcomeMessage();
      setStatus("Chat cleared.", false);
      setChatControlsDisabled(false);
    }}

    async function startNewChatSession() {{
      if (chatInFlight) return;
      if (
        storedMessages.length > 0 &&
        !window.confirm("Start a new chat session? Current messages will be cleared.")
      ) {{
        return;
      }}

      setChatControlsDisabled(true);
      sessionStorage.setItem(SESSION_STORAGE_KEY, String(Date.now()));
      await resetServerChat();
      storedMessages = [];
      saveStoredMessages([]);
      messages.innerHTML = "";
      showWelcomeMessage();
      setStatus("New chat session started.", false);
      setChatControlsDisabled(false);
    }}

    clearBtn?.addEventListener("click", clearChatSession);
    newSessionBtn?.addEventListener("click", startNewChatSession);

    function addMessage(role, text, isHtml) {{
      const el = document.createElement("div");
      el.className = "msg " + role;
      const label = document.createElement("div");
      label.className = "msg-label";
      label.textContent = role === "user" ? "You" : "Assistant";
      el.appendChild(label);
      const body = document.createElement("div");
      if (isHtml) {{
        body.innerHTML = text;
      }} else {{
        body.textContent = text;
      }}
      el.appendChild(body);
      messages.appendChild(el);
      messages.scrollTop = messages.scrollHeight;
      storedMessages.push({{ role, text, isHtml: !!isHtml }});
      saveStoredMessages(storedMessages);
    }}

    if (storedMessages.length === 0) {{
      showWelcomeMessage();
    }} else {{
      renderStoredMessages();
    }}

    form.addEventListener("submit", async (e) => {{
      e.preventDefault();
      const text = input.value.trim();
      if (!text || chatInFlight) return;

      const endpoint = chatEndpoint();
      if (!endpoint) {{
        addMessage(
          "assistant",
          "Chat only works when this page is served by FastAPI at " +
            apiBase +
            "/ — not when opening report.html from disk.",
          false
        );
        return;
      }}

      chatInFlight = true;
      setChatControlsDisabled(true);
      addMessage("user", text, false);
      input.value = "";
      sendBtn.disabled = true;
      sendBtn.classList.add("loading");
      sendBtn.textContent = "Sending";
      showThinking();
      reportMain?.classList.add("main-updating");

      try {{
        setStatus("Step 1/2 — refreshing data from Supabase...", true);
        const refreshed = await tryRefreshData();
        setStatus(
          (refreshed ? "Data refreshed. " : "Using cached data. ") +
            "Step 2/2 — waiting for AI (may take several minutes on CPU)...",
          true
        );

        const data = await postChat(text, true);
        removeThinking();
        if (data.summary) {{
          updateReportPane(data.summary, data.record_count);
        }}
        const suffix = data.source ? " [" + data.source + "]" : "";
        addMessage("assistant", data.reply, true);
        setStatus("Done" + suffix + (data.record_count ? " · " + data.record_count + " records" : ""), false);
        if (data.trigger_download) {{
          await downloadChatReport();
        }}
      }} catch (err) {{
        removeThinking();
        addMessage("assistant", "Error: " + formatFetchError(err), false);
        setStatus("", false);
      }} finally {{
        chatInFlight = false;
        setChatControlsDisabled(false);
        reportMain?.classList.remove("main-updating");
        sendBtn.disabled = false;
        sendBtn.classList.remove("loading");
        sendBtn.textContent = "Send";
        input.focus();
      }}
    }});

    function isExportPhrase(text) {{
      const t = (text || "").toLowerCase();
      return [
        "download report", "download chat", "export report", "export chat",
        "save report", "get report", "下載報告", "下载报告", "導出報告", "导出报告",
      ].some((phrase) => t.includes(phrase));
    }}

    function countUserQuestions() {{
      return storedMessages.filter(
        (m) => m.role === "user" && !isExportPhrase(m.text)
      ).length;
    }}

    function parseDownloadFilename(header) {{
      if (!header) return null;
      const match = /filename=\"?([^\";]+)\"?/i.exec(header);
      return match ? match[1] : null;
    }}

    async function downloadChatReport() {{
      if (countUserQuestions() === 0) {{
        setStatus("Ask at least one data question before downloading.", false);
        return;
      }}

      const url = apiUrl("/api/chat/export");
      if (!url) {{
        setStatus("Download requires the report opened via " + apiBase + "/", false);
        return;
      }}

      downloadBtn.disabled = true;
      setStatus("Preparing chat report download...", true);
      try {{
        const res = await fetchWithTimeout(
          url,
          fetchOptions("POST", {{ messages: storedMessages }}),
          60000
        );
        if (!res.ok) {{
          const err = await res.json().catch(() => ({{}}));
          throw new Error(formatErrorDetail(err.detail) || "Export failed (HTTP " + res.status + ")");
        }}
        const blob = await res.blob();
        const filename =
          parseDownloadFilename(res.headers.get("Content-Disposition")) ||
          ("tree-chat-report-" + new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") + ".html");
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(link.href);
        setStatus("Downloaded " + filename, false);
      }} catch (err) {{
        setStatus("", false);
        addMessage("assistant", "Error: Could not download report — " + err.message, false);
      }} finally {{
        downloadBtn.disabled = false;
      }}
    }}

    downloadBtn?.addEventListener("click", downloadChatReport);

    const testFilter = document.getElementById("test-filter");
    const testCardsGrid = document.getElementById("test-cards-grid");
    if (testFilter && testCardsGrid) {{
      testFilter.addEventListener("change", () => {{
        const value = testFilter.value;
        testCardsGrid.querySelectorAll(".test-card").forEach((card) => {{
          const group = card.getAttribute("data-group") || "";
          const show = value === "all" || group === value;
          card.classList.toggle("is-hidden", !show);
        }});
      }});
    }}
    document.querySelectorAll(".test-try-btn").forEach((btn) => {{
      btn.addEventListener("click", () => {{
        const q = btn.getAttribute("data-question");
        if (!q || !input) return;
        input.value = q;
        input.focus();
        chatSidebar?.scrollIntoView({{ behavior: "smooth", block: "nearest" }});
        setStatus("Question copied to chat — press Send to test.", false);
      }});
    }});
  </script>
</body>
</html>
"""
