
    const configuredApiBase = document.querySelector('meta[name="api-base-url"]')?.content
      || "http://127.0.0.1:8000";
    const chatTimeoutSec = parseInt(
      document.querySelector('meta[name="chat-timeout-seconds"]')?.content || "300",
      10
    );
    const clientTimeoutMs = (chatTimeoutSec + 120) * 1000;
    const isFilePage = window.location.protocol === "file:";
    const apiBase = configuredApiBase.replace(/\/$/, "");

    function isFastApiOrigin() {
      if (isFilePage) return false;
      const host = window.location.hostname;
      const local = host === "127.0.0.1" || host === "localhost" || host === "[::1]";
      return local && window.location.port === "8000";
    }

    function isCrossOriginPreview() {
      return !isFilePage && !isFastApiOrigin();
    }

    /** FastAPI on :8000 → same-origin /api/... ; Live Server etc. → full URL to uvicorn. */
    function apiUrl(path) {
      if (isFilePage) return null;
      if (isFastApiOrigin()) return path;
      return apiBase + path;
    }

    function chatEndpoint() {
      return apiUrl("/api/chat");
    }

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

    function setStatus(text, busy) {
      statusEl.textContent = text || "";
      statusEl.classList.toggle("busy", !!busy);
    }

    if (isFilePage) {
      fileWarning.style.display = "block";
      fileWarning.innerHTML =
        "<strong>Chat disabled:</strong> this page was opened as a local file " +
        "(<code>file://</code>). Browsers block that from calling the API. " +
        "Open " +
        '<a href="' + apiBase + '/" target="_blank" rel="noopener">' +
        apiBase + "/</a> instead (keep the server running).";
    } else if (isCrossOriginPreview()) {
      liveServerInfo.style.display = "block";
      liveServerInfo.innerHTML =
        "Preview server detected (<code>" + window.location.origin + "</code>). " +
        "Chat will call <strong>" + apiBase + "</strong> — keep uvicorn running there. " +
        'Simplest option: <a href="' + apiBase + '/">' + apiBase + "/</a>";
    }

    async function checkApiConnection() {
      if (isFilePage) {
        setStatus("Not connected — open via " + apiBase + "/", false);
        return false;
      }
      const healthUrl = apiUrl("/api/health");
      try {
        const res = await fetch(healthUrl, {
          method: "GET",
          credentials: isFastApiOrigin() ? "same-origin" : "omit",
          mode: "cors",
        });
        if (!res.ok) throw new Error("HTTP " + res.status);
        setStatus("Connected to API at " + apiBase, false);
        statusEl.classList.add("conn-ok");
        return true;
      } catch (err) {
        setStatus(
          "Cannot reach API at " + apiBase +
          " — start uvicorn (port 8000), then reload this page.",
          false
        );
        statusEl.classList.add("conn-bad");
        console.error("API health check failed:", healthUrl, err);
        return false;
      }
    }

    const reportMain = document.getElementById("report-main");
    const reportOverview = document.getElementById("report-overview");
    const reportTables = document.getElementById("report-tables");
    const reportDataUpdated = document.getElementById("report-data-updated");
    const tableSections = JSON.parse(
      document.querySelector('meta[name="report-table-sections"]')?.content || "[]"
    );

    function escapeHtml(text) {
      const el = document.createElement("span");
      el.textContent = text == null ? "" : String(text);
      return el.innerHTML;
    }

    function buildOverviewHtml(summary) {
      const dr = summary.date_range || ["—", "—"];
      return (
        '<section class="card">' +
        "<h2>Overview</h2><ul>" +
        "<li><strong>Total cases:</strong> " + (summary.total_cases || 0) + "</li>" +
        "<li><strong>Total trees:</strong> " + (summary.total_trees || 0) + "</li>" +
        "<li><strong>Date range:</strong> " + escapeHtml(dr[0]) + " → " + escapeHtml(dr[1]) + "</li>" +
        "</ul></section>"
      );
    }

    function buildTableHtml(title, data) {
      const rows = Object.entries(data || {})
        .sort((a, b) => b[1] - a[1])
        .map(([k, v]) => "<tr><td>" + escapeHtml(k) + "</td><td>" + v + "</td></tr>")
        .join("");
      return (
        '<section class="card"><h2>' + escapeHtml(title) + "</h2>" +
        "<table><thead><tr><th>Category</th><th>Count</th></tr></thead>" +
        "<tbody>" + rows + "</tbody></table></section>"
      );
    }

    function updateReportPane(summary, recordCount) {
      if (!summary || !reportOverview || !reportTables) return;
      reportOverview.innerHTML = buildOverviewHtml(summary);
      reportTables.innerHTML = tableSections
        .filter((s) => summary[s.key])
        .map((s) => buildTableHtml(s.title, summary[s.key]))
        .join("");
      if (reportDataUpdated) {
        const n = recordCount != null ? recordCount : summary.total_cases || 0;
        reportDataUpdated.textContent =
          "Data updated · " + n + " records · " + new Date().toLocaleTimeString();
        reportDataUpdated.classList.add("flash");
        setTimeout(() => reportDataUpdated.classList.remove("flash"), 2500);
      }
    }

    async function loadLatestSummary() {
      const url = apiUrl("/api/summary");
      if (!url) return;
      try {
        const res = await fetch(url, {
          method: "GET",
          credentials: isFastApiOrigin() ? "same-origin" : "omit",
          mode: "cors",
        });
        if (!res.ok) return;
        const summary = await res.json();
        updateReportPane(summary, summary.total_cases);
      } catch (err) {
        console.warn("Could not load latest summary for report pane", err);
      }
    }

    if (!isFilePage) {
      checkApiConnection().then((ok) => {
        if (ok) loadLatestSummary();
      });
    }

    let thinkingEl = null;

    function showThinking() {
      removeThinking();
      thinkingEl = document.createElement("div");
      thinkingEl.className = "msg assistant thinking";
      thinkingEl.id = "chat-thinking";
      thinkingEl.innerHTML =
        '<div class="msg-label">Assistant</div>' +
        '<div>Working on your question…</div>';
      messages.appendChild(thinkingEl);
      messages.scrollTop = messages.scrollHeight;
    }

    function removeThinking() {
      if (thinkingEl) {
        thinkingEl.remove();
        thinkingEl = null;
      }
    }

    function formatFetchError(err) {
      if (err.name === "AbortError") {
        return (
          "Timed out in browser after " + Math.round(clientTimeoutMs / 1000) + "s. " +
          "Increase CHAT_TIMEOUT in .env or try a simpler question."
        );
      }
      if (err.message === "Failed to fetch") {
        if (isFilePage) {
          return (
            "Failed to fetch — you opened report.html as a file. " +
            "Use " + apiBase + "/ in the browser (not double-click report.html)."
          );
        }
        if (isCrossOriginPreview()) {
          return (
            "Failed to fetch — could not reach " + apiBase + " from Live Server. " +
            "Ensure uvicorn is running on port 8000, or open " + apiBase + "/ directly."
          );
        }
        return (
          "Failed to fetch — browser could not reach the API. " +
          "Use " + apiBase + "/ (not Live Server) if this keeps happening. " +
          "Also avoid --reload while chatting — server restarts drop in-flight requests."
        );
      }
      return err.message || String(err);
    }

    function formatErrorDetail(detail) {
      if (!detail) return "Request failed";
      if (typeof detail === "string") return detail;
      return JSON.stringify(detail);
    }

    let chatInFlight = false;
    const dataRefreshTimeoutMs = 90000;

    function fetchOptions(method, body) {
      const opts = {
        method,
        credentials: isFastApiOrigin() ? "same-origin" : "omit",
        mode: "cors",
      };
      if (body != null) {
        opts.headers = { "Content-Type": "application/json" };
        opts.body = JSON.stringify(body);
      }
      return opts;
    }

    function fetchWithTimeout(url, options, timeoutMs) {
      return new Promise((resolve, reject) => {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        fetch(url, { ...options, signal: controller.signal })
          .then(resolve)
          .catch(reject)
          .finally(() => clearTimeout(timer));
      });
    }

    async function parseJsonResponse(res) {
      const raw = await res.text();
      let data;
      try {
        data = JSON.parse(raw);
      } catch {
        throw new Error(
          "API returned non-JSON (status " + res.status + "). " +
          "Reload from " + (isFastApiOrigin() ? window.location.origin : apiBase) + "/"
        );
      }
      if (!res.ok) throw new Error(formatErrorDetail(data.detail));
      return data;
    }

    async function tryRefreshData() {
      const url = apiUrl("/api/data/refresh");
      if (!url) return false;
      try {
        const res = await fetchWithTimeout(
          url,
          fetchOptions("POST", {}),
          dataRefreshTimeoutMs
        );
        const data = await parseJsonResponse(res);
        if (data.summary) updateReportPane(data.summary, data.record_count);
        return true;
      } catch (err) {
        console.warn("Data refresh failed; continuing with cached data", err);
        return false;
      }
    }

    async function postChat(text, allowRetry) {
      const endpoint = chatEndpoint();
      try {
        const res = await fetchWithTimeout(
          endpoint,
          fetchOptions("POST", { message: text, refresh_data: false }),
          clientTimeoutMs
        );
        return parseJsonResponse(res);
      } catch (err) {
        if (allowRetry && err.message === "Failed to fetch") {
          setStatus("Connection dropped — retrying once...", true);
          await new Promise((resolve) => setTimeout(resolve, 2000));
          return postChat(text, false);
        }
        throw err;
      }
    }

    const SESSION_STORAGE_KEY = "deepseektree_session_id";
    const SIDEBAR_WIDTH_KEY = "deepseektree_sidebar_width";
    const CHAT_HEIGHT_KEY = "deepseektree_chat_height";
    const LEGACY_CHAT_KEY = "deepseektree_chat_history";

    function getSessionId() {
      let id = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (!id) {
        id = String(Date.now());
        sessionStorage.setItem(SESSION_STORAGE_KEY, id);
      }
      return id;
    }

    function chatStorageKey() {
      return "deepseektree_chat_" + getSessionId();
    }

    function migrateLegacyChat() {
      try {
        const legacy = sessionStorage.getItem(LEGACY_CHAT_KEY);
        if (!legacy) return;
        const key = chatStorageKey();
        if (!sessionStorage.getItem(key)) {
          sessionStorage.setItem(key, legacy);
        }
        sessionStorage.removeItem(LEGACY_CHAT_KEY);
      } catch (err) {
        console.warn("Could not migrate legacy chat storage", err);
      }
    }

    migrateLegacyChat();

    function loadStoredMessages() {
      try {
        const raw = sessionStorage.getItem(chatStorageKey());
        return raw ? JSON.parse(raw) : [];
      } catch {
        return [];
      }
    }

    function saveStoredMessages(items) {
      try {
        sessionStorage.setItem(chatStorageKey(), JSON.stringify(items));
      } catch (err) {
        console.warn("Could not save chat history", err);
      }
    }

    function isStackedLayout() {
      return window.matchMedia("(max-width: 900px)").matches;
    }

    function clampSidebarWidth(px) {
      const min = 260;
      const max = Math.min(Math.floor(window.innerWidth * 0.75), window.innerWidth - 280);
      return Math.max(min, Math.min(px, Math.max(min, max)));
    }

    function clampChatHeight(px) {
      const min = 220;
      const max = Math.min(Math.floor(window.innerHeight * 0.85), window.innerHeight - 200);
      return Math.max(min, Math.min(px, Math.max(min, max)));
    }

    function applySidebarWidth(px, persist) {
      const w = clampSidebarWidth(px);
      document.documentElement.style.setProperty("--sidebar-width", w + "px");
      if (persist) localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w));
      return w;
    }

    function applyChatHeight(px, persist) {
      const h = clampChatHeight(px);
      document.documentElement.style.setProperty("--chat-pane-height", h + "px");
      if (persist) localStorage.setItem(CHAT_HEIGHT_KEY, String(h));
      return h;
    }

    function loadPaneSizes() {
      const savedWidth = parseInt(localStorage.getItem(SIDEBAR_WIDTH_KEY) || "", 10);
      if (!Number.isNaN(savedWidth)) applySidebarWidth(savedWidth, false);
      const savedHeight = parseInt(localStorage.getItem(CHAT_HEIGHT_KEY) || "", 10);
      if (!Number.isNaN(savedHeight)) applyChatHeight(savedHeight, false);
    }

    loadPaneSizes();

    let resizeMode = null;
    let resizeStart = 0;
    let resizeStartSize = 0;

    function onResizeMove(clientX, clientY) {
      if (!resizeMode) return;
      if (resizeMode === "sidebar") {
        const delta = resizeStart - clientX;
        applySidebarWidth(resizeStartSize + delta, true);
      } else if (resizeMode === "chat-height") {
        const delta = clientY - resizeStart;
        applyChatHeight(resizeStartSize + delta, true);
      }
    }

    function stopResize() {
      resizeMode = null;
      appLayout?.classList.remove("is-resizing");
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", stopResize);
      document.removeEventListener("touchmove", onTouchMove);
      document.removeEventListener("touchend", stopResize);
    }

    function onMouseMove(e) {
      onResizeMove(e.clientX, e.clientY);
    }

    function onTouchMove(e) {
      if (!e.touches.length) return;
      e.preventDefault();
      onResizeMove(e.touches[0].clientX, e.touches[0].clientY);
    }

    function startResize(e) {
      if (e.type === "mousedown" && e.button !== 0) return;
      if (isStackedLayout()) {
        resizeMode = "chat-height";
        resizeStart = e.touches ? e.touches[0].clientY : e.clientY;
        const h = parseInt(
          getComputedStyle(document.documentElement).getPropertyValue("--chat-pane-height"),
          10
        );
        resizeStartSize = Number.isNaN(h) ? chatSidebar.offsetHeight : h;
      } else {
        resizeMode = "sidebar";
        resizeStart = e.touches ? e.touches[0].clientX : e.clientX;
        resizeStartSize = chatSidebar.offsetWidth;
      }
      appLayout?.classList.add("is-resizing");
      if (e.type === "touchstart") {
        document.addEventListener("touchmove", onTouchMove, { passive: false });
        document.addEventListener("touchend", stopResize);
      } else {
        document.addEventListener("mousemove", onMouseMove);
        document.addEventListener("mouseup", stopResize);
      }
      e.preventDefault();
    }

    paneResizer?.addEventListener("mousedown", startResize);
    paneResizer?.addEventListener("touchstart", startResize, { passive: false });

    paneResizer?.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 40 : 16;
      if (isStackedLayout()) {
        const current = parseInt(
          getComputedStyle(document.documentElement).getPropertyValue("--chat-pane-height"),
          10
        ) || chatSidebar.offsetHeight;
        if (e.key === "ArrowUp") {
          applyChatHeight(current - step, true);
          e.preventDefault();
        } else if (e.key === "ArrowDown") {
          applyChatHeight(current + step, true);
          e.preventDefault();
        }
      } else {
        const current = chatSidebar.offsetWidth;
        if (e.key === "ArrowLeft") {
          applySidebarWidth(current + step, true);
          e.preventDefault();
        } else if (e.key === "ArrowRight") {
          applySidebarWidth(current - step, true);
          e.preventDefault();
        }
      }
    });

    window.addEventListener("resize", () => {
      if (!isStackedLayout()) {
        const w = chatSidebar.offsetWidth;
        applySidebarWidth(w, false);
      } else {
        const h = chatSidebar.offsetHeight;
        applyChatHeight(h, false);
      }
    });

    let storedMessages = loadStoredMessages();

    function showWelcomeMessage() {
      const welcomeEl = document.getElementById("chat-welcome-data");
      const welcomeHtml = welcomeEl
        ? JSON.parse(welcomeEl.textContent || '""')
        : "Ask about districts, severity, dates, or totals in this dataset.";
      addMessage("assistant", welcomeHtml, true);
      storedMessages = loadStoredMessages();
    }

    function renderStoredMessages() {
      messages.innerHTML = "";
      storedMessages.forEach((item) => {
        const el = document.createElement("div");
        el.className = "msg " + item.role;
        const label = document.createElement("div");
        label.className = "msg-label";
        label.textContent = item.role === "user" ? "You" : "Assistant";
        el.appendChild(label);
        const body = document.createElement("div");
        if (item.isHtml) {
          body.innerHTML = item.text;
        } else {
          body.textContent = item.text;
        }
        el.appendChild(body);
        messages.appendChild(el);
      });
      messages.scrollTop = messages.scrollHeight;
    }

    async function resetServerChat() {
      const url = apiUrl("/api/chat/reset");
      if (!url) return;
      try {
        await fetchWithTimeout(url, fetchOptions("POST", {}), 15000);
      } catch (err) {
        console.warn("Could not reset server chat context", err);
      }
    }

    function setChatControlsDisabled(disabled) {
      if (clearBtn) clearBtn.disabled = disabled;
      if (newSessionBtn) newSessionBtn.disabled = disabled;
      if (downloadBtn) downloadBtn.disabled = disabled;
    }

    async function clearChatSession() {
      if (chatInFlight) return;
      if (storedMessages.length === 0) {
        setStatus("Chat is already empty.", false);
        return;
      }
      if (!window.confirm("Clear all messages in this chat session?")) return;

      setChatControlsDisabled(true);
      await resetServerChat();
      storedMessages = [];
      saveStoredMessages([]);
      messages.innerHTML = "";
      showWelcomeMessage();
      setStatus("Chat cleared.", false);
      setChatControlsDisabled(false);
    }

    async function startNewChatSession() {
      if (chatInFlight) return;
      if (
        storedMessages.length > 0 &&
        !window.confirm("Start a new chat session? Current messages will be cleared.")
      ) {
        return;
      }

      setChatControlsDisabled(true);
      sessionStorage.setItem(SESSION_STORAGE_KEY, String(Date.now()));
      await resetServerChat();
      storedMessages = [];
      saveStoredMessages([]);
      messages.innerHTML = "";
      showWelcomeMessage();
      setStatus("New chat session started.", false);
      setChatControlsDisabled(false);
    }

    clearBtn?.addEventListener("click", clearChatSession);
    newSessionBtn?.addEventListener("click", startNewChatSession);

    function addMessage(role, text, isHtml) {
      const el = document.createElement("div");
      el.className = "msg " + role;
      const label = document.createElement("div");
      label.className = "msg-label";
      label.textContent = role === "user" ? "You" : "Assistant";
      el.appendChild(label);
      const body = document.createElement("div");
      if (isHtml) {
        body.innerHTML = text;
      } else {
        body.textContent = text;
      }
      el.appendChild(body);
      messages.appendChild(el);
      messages.scrollTop = messages.scrollHeight;
      storedMessages.push({ role, text, isHtml: !!isHtml });
      saveStoredMessages(storedMessages);
    }

    if (storedMessages.length === 0) {
      showWelcomeMessage();
    } else {
      renderStoredMessages();
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text || chatInFlight) return;

      const endpoint = chatEndpoint();
      if (!endpoint) {
        addMessage(
          "assistant",
          "Chat only works when this page is served by FastAPI at " +
            apiBase +
            "/ — not when opening report.html from disk.",
          false
        );
        return;
      }

      chatInFlight = true;
      setChatControlsDisabled(true);
      addMessage("user", text, false);
      input.value = "";
      sendBtn.disabled = true;
      sendBtn.classList.add("loading");
      sendBtn.textContent = "Sending";
      showThinking();
      reportMain?.classList.add("main-updating");

      try {
        setStatus("Step 1/2 — refreshing data from Supabase...", true);
        const refreshed = await tryRefreshData();
        setStatus(
          (refreshed ? "Data refreshed. " : "Using cached data. ") +
            "Step 2/2 — waiting for AI (may take several minutes on CPU)...",
          true
        );

        const data = await postChat(text, true);
        removeThinking();
        if (data.summary) {
          updateReportPane(data.summary, data.record_count);
        }
        const suffix = data.source ? " [" + data.source + "]" : "";
        addMessage("assistant", data.reply, true);
        setStatus("Done" + suffix + (data.record_count ? " · " + data.record_count + " records" : ""), false);
        if (data.trigger_download) {
          await downloadChatReport();
        }
      } catch (err) {
        removeThinking();
        addMessage("assistant", "Error: " + formatFetchError(err), false);
        setStatus("", false);
      } finally {
        chatInFlight = false;
        setChatControlsDisabled(false);
        reportMain?.classList.remove("main-updating");
        sendBtn.disabled = false;
        sendBtn.classList.remove("loading");
        sendBtn.textContent = "Send";
        input.focus();
      }
    });

    function isExportPhrase(text) {
      const t = (text || "").toLowerCase();
      return [
        "download report", "download chat", "export report", "export chat",
        "save report", "get report", "下載報告", "下载报告", "導出報告", "导出报告",
      ].some((phrase) => t.includes(phrase));
    }

    function countUserQuestions() {
      return storedMessages.filter(
        (m) => m.role === "user" && !isExportPhrase(m.text)
      ).length;
    }

    function parseDownloadFilename(header) {
      if (!header) return null;
      const match = /filename="?([^";]+)"?/i.exec(header);
      return match ? match[1] : null;
    }

    async function downloadChatReport() {
      if (countUserQuestions() === 0) {
        setStatus("Ask at least one data question before downloading.", false);
        return;
      }

      const url = apiUrl("/api/chat/export");
      if (!url) {
        setStatus("Download requires the report opened via " + apiBase + "/", false);
        return;
      }

      downloadBtn.disabled = true;
      setStatus("Preparing chat report download...", true);
      try {
        const res = await fetchWithTimeout(
          url,
          fetchOptions("POST", { messages: storedMessages }),
          60000
        );
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(formatErrorDetail(err.detail) || "Export failed (HTTP " + res.status + ")");
        }
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
      } catch (err) {
        setStatus("", false);
        addMessage("assistant", "Error: Could not download report — " + err.message, false);
      } finally {
        downloadBtn.disabled = false;
      }
    }

    downloadBtn?.addEventListener("click", downloadChatReport);
  