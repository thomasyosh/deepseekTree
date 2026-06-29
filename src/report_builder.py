import html
import json
from typing import Any

import config


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


def build_report_html(summary: dict[str, Any], narrative: str) -> str:
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
        for key, title in [
            ("by_district", "Cases by District"),
            ("by_status", "Cases by Status"),
            ("by_severity", "Cases by Severity"),
            ("by_complaint_type", "Cases by Complaint Type"),
            ("by_contractor", "Cases by Contractor"),
        ]
        if key in summary
    )

    safe_narrative = narrative.strip() or "<p>No narrative generated.</p>"
    api_base = html.escape(config.API_BASE_URL)

    return f"""<!DOCTYPE html>
<html lang="zh-HK">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="chat-timeout-seconds" content="{config.CHAT_TIMEOUT}" />
  <meta name="api-base-url" content="{api_base}" />
  <title>Tree Complaint Analysis Report</title>
  <style>
    :root {{
      --bg: #f4f6f8;
      --card: #ffffff;
      --text: #1a1a2e;
      --muted: #5c6370;
      --accent: #2563eb;
      --border: #e5e7eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    .layout {{
      display: grid;
      grid-template-columns: 1fr 380px;
      min-height: 100vh;
    }}
    .main {{ padding: 2rem; overflow-y: auto; }}
    .sidebar {{
      background: var(--card);
      border-left: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      height: 100vh;
      position: sticky;
      top: 0;
    }}
    h1 {{ margin-top: 0; }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem;
      margin-bottom: 1rem;
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      text-align: left;
      padding: 0.5rem 0.75rem;
      border-bottom: 1px solid var(--border);
    }}
    .narrative {{ line-height: 1.6; }}
    .chat-header {{
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--border);
      font-weight: 600;
    }}
    .chat-messages {{
      flex: 1;
      overflow-y: auto;
      padding: 1rem 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
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
      padding: 1rem;
      border-top: 1px solid var(--border);
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
    .conn-ok {{ color: #15803d; }}
    .conn-bad {{ color: #b91c1c; }}
    @media (max-width: 900px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .sidebar {{ height: 50vh; position: static; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <main class="main">
      <h1>Tree Complaint Analysis Report</h1>
      {overview}
      {tables}
      <section class="card narrative">
        <h2>AI Analysis</h2>
        {safe_narrative}
      </section>
    </main>
    <aside class="sidebar">
      <div class="chat-header">Chat with AI Analyst</div>
      <div id="file-warning" class="file-warning"></div>
      <div id="chat-status" class="chat-status"></div>
      <div id="chat-messages" class="chat-messages"></div>
      <form id="chat-form" class="chat-input">
        <input id="chat-input" type="text" placeholder="e.g. Which district has the most severe cases?" autocomplete="off" />
        <button type="submit" id="chat-send">Send</button>
      </form>
    </aside>
  </div>
  <script>
    const configuredApiBase = document.querySelector('meta[name="api-base-url"]')?.content
      || "{api_base}";
    const chatTimeoutSec = parseInt(
      document.querySelector('meta[name="chat-timeout-seconds"]')?.content || "300",
      10
    );
    const clientTimeoutMs = (chatTimeoutSec + 120) * 1000;

    const clientTimeoutMs = (chatTimeoutSec + 120) * 1000;
    const isFilePage = window.location.protocol === "file:";

    /** Same-origin relative path when served over HTTP — avoids CORS / wrong host. */
    function chatEndpoint() {{
      if (isFilePage) return null;
      if (window.location.protocol === "http:" || window.location.protocol === "https:") {{
        return "/api/chat";
      }}
      return configuredApiBase.replace(/\\/$/, "") + "/api/chat";
    }}

    const statusEl = document.getElementById("chat-status");
    const fileWarning = document.getElementById("file-warning");

    if (isFilePage) {{
      fileWarning.style.display = "block";
      fileWarning.innerHTML =
        "<strong>Chat disabled:</strong> this page was opened as a local file " +
        "(<code>file://</code>). Browsers block that from calling the API. " +
        "Open " +
        '<a href="' + configuredApiBase + '/" target="_blank" rel="noopener">' +
        configuredApiBase + "/</a> instead (keep the server running).";
    }}

    async function checkApiConnection() {{
      if (isFilePage) {{
        setStatus("Not connected — open via " + configuredApiBase + "/", false);
        return false;
      }}
      try {{
        const res = await fetch("/api/health", {{ method: "GET", credentials: "same-origin" }});
        if (!res.ok) throw new Error("HTTP " + res.status);
        setStatus("Connected to API at " + window.location.origin, false);
        statusEl.classList.add("conn-ok");
        return true;
      }} catch (err) {{
        setStatus(
          "Cannot reach API at " + window.location.origin +
          " — start the server, then reload this page.",
          false
        );
        statusEl.classList.add("conn-bad");
        console.error("API health check failed:", err);
        return false;
      }}
    }}

    checkApiConnection();

    function setStatus(text, busy) {{
      statusEl.textContent = text || "";
      statusEl.classList.toggle("busy", !!busy);
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
            "Use " + configuredApiBase + "/ in the browser (not double-click report.html)."
          );
        }}
        return (
          "Failed to fetch — browser could not reach the API. " +
          "Confirm the server is running at " + window.location.origin +
          ", reload this page, and check DevTools → Network for /api/chat."
        );
      }}
      return err.message || String(err);
    }}

    function formatErrorDetail(detail) {{
      if (!detail) return "Request failed";
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail);
    }}

    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const sendBtn = document.getElementById("chat-send");
    const messages = document.getElementById("chat-messages");
    const CHAT_STORAGE_KEY = "deepseektree_chat_history";

    function loadStoredMessages() {{
      try {{
        const raw = sessionStorage.getItem(CHAT_STORAGE_KEY);
        return raw ? JSON.parse(raw) : [];
      }} catch {{
        return [];
      }}
    }}

    function saveStoredMessages(items) {{
      try {{
        sessionStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(items));
      }} catch (err) {{
        console.warn("Could not save chat history", err);
      }}
    }}

    let storedMessages = loadStoredMessages();

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
      addMessage(
        "assistant",
        "Ask questions about districts, severity, status, or trends in this dataset.",
        false
      );
      storedMessages = loadStoredMessages();
    }} else {{
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

    form.addEventListener("submit", async (e) => {{
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;

      const endpoint = chatEndpoint();
      if (!endpoint) {{
        addMessage(
          "assistant",
          "Chat only works when this page is served by FastAPI at " +
            configuredApiBase +
            "/ — not when opening report.html from disk.",
          false
        );
        return;
      }}

      addMessage("user", text, false);
      input.value = "";
      sendBtn.disabled = true;
      sendBtn.classList.add("loading");
      sendBtn.textContent = "Sending";
      showThinking();
      setStatus(
        "Request sent — refreshing data, then waiting for Ollama (may take several minutes on CPU).",
        true
      );

      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), clientTimeoutMs);

      try {{
        const res = await fetch(endpoint, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ message: text }}),
          credentials: "same-origin",
          signal: controller.signal,
        }});
        const raw = await res.text();
        let data;
        try {{
          data = JSON.parse(raw);
        }} catch {{
          throw new Error(
            "API returned non-JSON (status " + res.status + "). " +
            "Reload from " + window.location.origin + "/ (not a saved report.html file)."
          );
        }}
        if (!res.ok) throw new Error(formatErrorDetail(data.detail));
        removeThinking();
        const suffix = data.source ? " [" + data.source + "]" : "";
        addMessage("assistant", data.reply, true);
        setStatus("Done" + suffix + (data.record_count ? " · " + data.record_count + " records" : ""), false);
      }} catch (err) {{
        removeThinking();
        addMessage("assistant", "Error: " + formatFetchError(err), false);
        setStatus("", false);
      }} finally {{
        clearTimeout(timer);
        sendBtn.disabled = false;
        sendBtn.classList.remove("loading");
        sendBtn.textContent = "Send";
        input.focus();
      }}
    }});
  </script>
</body>
</html>
"""
