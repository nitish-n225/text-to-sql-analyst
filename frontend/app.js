/**
 * Text-to-SQL Analyst - Frontend Application Logic
 */

// Application State
const state = {
  activeDb: "ecommerce.db",
  databases: [],
  prompts: {},
  simulateError: false,
  aiSettings: {
    provider: "offline",
    apiKey: "",
    model: "",
    baseUrl: "",
    maxRetries: 3
  },
  lastAnalysis: null,
  currentChart: null,
  activeChartType: "bar",
  isDarkTheme: true
};

// DOM Elements
const elements = {
  dbSelect: document.getElementById("db-select"),
  btnInspectSchema: document.getElementById("btn-inspect-schema"),
  simulateErrorToggle: document.getElementById("simulate-error-toggle"),
  btnOpenSettings: document.getElementById("btn-open-settings"),
  btnOpenUpload: document.getElementById("btn-open-upload"),
  btnThemeToggle: document.getElementById("btn-theme-toggle"),
  themeIcon: document.getElementById("theme-icon"),
  
  queryInput: document.getElementById("natural-query-input"),
  btnClearQuery: document.getElementById("btn-clear-query"),
  btnExecuteQuery: document.getElementById("btn-execute-query"),
  promptChipsContainer: document.getElementById("prompt-chips-container"),

  welcomeSection: document.getElementById("welcome-section"),
  retryLoopSection: document.getElementById("retry-loop-section"),
  resultsSection: document.getElementById("results-section"),

  loopDot: document.getElementById("loop-dot"),
  loopTitle: document.getElementById("loop-title"),
  attemptBadge: document.getElementById("attempt-badge"),
  loopDuration: document.getElementById("loop-duration"),
  btnToggleTrace: document.getElementById("btn-toggle-trace"),
  retryTimeline: document.getElementById("retry-timeline"),

  questionEcho: document.getElementById("question-echo"),
  answerPills: document.getElementById("answer-pills"),
  answerText: document.getElementById("answer-text"),
  overviewSqlCode: document.getElementById("overview-sql-code"),
  btnJumpSql: document.getElementById("btn-jump-sql"),
  
  tabBtns: document.querySelectorAll(".tab-btn"),
  tabPanes: document.querySelectorAll(".tab-pane"),
  btnCopySql: document.getElementById("btn-copy-sql"),
  btnExportCsv: document.getElementById("btn-export-csv"),

  analyticsChart: document.getElementById("analytics-chart"),
  noChartMsg: document.getElementById("no-chart-msg"),
  chartTypeBtns: document.querySelectorAll(".chart-type-btn"),
  
  tableSearch: document.getElementById("table-search"),
  tableHead: document.getElementById("table-head"),
  tableBody: document.getElementById("table-body"),
  tableStats: document.getElementById("table-stats"),
  resultRowCount: document.getElementById("result-row-count"),

  fullSqlCode: document.getElementById("full-sql-code"),
  sqlTimeTag: document.getElementById("sql-time-tag"),
  btnExplainPlan: document.getElementById("btn-explain-plan"),
  explainPlanContainer: document.getElementById("explain-plan-container"),
  explainPlanOutput: document.getElementById("explain-plan-output"),

  sandboxTextarea: document.getElementById("sandbox-textarea"),
  btnRunSandbox: document.getElementById("btn-run-sandbox"),
  sandboxResultArea: document.getElementById("sandbox-result-area"),

  modalSchema: document.getElementById("modal-schema"),
  btnCloseSchema: document.getElementById("btn-close-schema"),
  schemaModalBody: document.getElementById("schema-modal-body"),
  schemaModalTitle: document.getElementById("schema-modal-title"),

  modalSettings: document.getElementById("modal-settings"),
  btnCloseSettings: document.getElementById("btn-close-settings"),
  settingProvider: document.getElementById("setting-provider"),
  settingApiKey: document.getElementById("setting-api-key"),
  settingModel: document.getElementById("setting-model"),
  settingBaseUrl: document.getElementById("setting-base-url"),
  settingMaxRetries: document.getElementById("setting-max-retries"),
  maxRetriesVal: document.getElementById("max-retries-val"),
  btnToggleKeyVis: document.getElementById("btn-toggle-key-vis"),
  btnSaveSettings: document.getElementById("btn-save-settings"),

  modalUpload: document.getElementById("modal-upload"),
  btnCloseUpload: document.getElementById("btn-close-upload"),
  uploadTabs: document.querySelectorAll(".upload-tab"),
  uploadPanes: document.querySelectorAll(".upload-pane"),
  dbDropZone: document.getElementById("db-drop-zone"),
  dbFileInput: document.getElementById("db-file-input"),
  dbUploadStatus: document.getElementById("db-upload-status"),
  csvDropZone: document.getElementById("csv-drop-zone"),
  csvFileInput: document.getElementById("csv-file-input"),
  csvTableName: document.getElementById("csv-table-name"),
  csvUploadStatus: document.getElementById("csv-upload-status"),
  btnConfirmReset: document.getElementById("btn-confirm-reset"),

  toastContainer: document.getElementById("toast-container")
};

// Initialize Application
async function init() {
  loadSavedSettings();
  setupEventListeners();
  await loadDatabases();
  await loadPrompts();
  renderPromptChips();
  lucide.createIcons();
}

// Load Settings from LocalStorage
function loadSavedSettings() {
  try {
    const saved = localStorage.getItem("t2sql_settings");
    if (saved) {
      state.aiSettings = { ...state.aiSettings, ...JSON.parse(saved) };
    }
    const savedTheme = localStorage.getItem("t2sql_theme");
    if (savedTheme === "light") {
      state.isDarkTheme = false;
      document.body.classList.replace("dark-theme", "light-theme");
      elements.themeIcon.setAttribute("data-lucide", "sun");
    }
  } catch (e) {
    console.error("Failed to load saved settings", e);
  }
}

function saveSettings() {
  localStorage.setItem("t2sql_settings", JSON.stringify(state.aiSettings));
}

// Setup Event Listeners
function setupEventListeners() {
  // DB Selector
  elements.dbSelect.addEventListener("change", async (e) => {
    const newDb = e.target.value;
    try {
      const res = await fetch("/api/databases/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ db_name: newDb })
      });
      if (res.ok) {
        state.activeDb = newDb;
        renderPromptChips();
        showToast(`Switched active database to ${newDb}`, "success");
      }
    } catch (err) {
      showToast("Error switching database", "error");
    }
  });

  // Simulation Toggle
  elements.simulateErrorToggle.addEventListener("change", (e) => {
    state.simulateError = e.target.checked;
    if (state.simulateError) {
      showToast("Test Self-Correction mode enabled: Deliberate error will trigger and self-heal on your next query!", "success");
    } else {
      showToast("Test Self-Correction mode disabled.", "info");
    }
  });

  // Natural Language Input & Execution
  elements.btnExecuteQuery.addEventListener("click", executeNaturalQuery);
  elements.queryInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      executeNaturalQuery();
    }
  });

  elements.btnClearQuery.addEventListener("click", () => {
    elements.queryInput.value = "";
    elements.queryInput.focus();
  });

  // Tabs Navigation
  elements.tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      elements.tabBtns.forEach(b => b.classList.remove("active"));
      elements.tabPanes.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      const targetPane = document.getElementById(btn.dataset.tab);
      if (targetPane) targetPane.classList.add("active");
    });
  });

  // Jump from Overview to SQL Tab
  elements.btnJumpSql.addEventListener("click", () => {
    const sqlTabBtn = document.querySelector('[data-tab="tab-playground"]');
    if (sqlTabBtn) sqlTabBtn.click();
  });

  // Chart Type Buttons
  elements.chartTypeBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      elements.chartTypeBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeChartType = btn.dataset.chart;
      if (state.lastAnalysis && state.lastAnalysis.chart_data) {
        renderChart(state.lastAnalysis.chart_data, state.activeChartType);
      }
    });
  });

  // In-table Search Filter
  elements.tableSearch.addEventListener("input", filterTableRows);

  // Copy SQL
  elements.btnCopySql.addEventListener("click", () => {
    if (state.lastAnalysis && state.lastAnalysis.query_used) {
      navigator.clipboard.writeText(state.lastAnalysis.query_used);
      showToast("SQL Query copied to clipboard!", "success");
    }
  });

  // Export CSV
  elements.btnExportCsv.addEventListener("click", exportResultsToCsv);

  // Explain Query Plan
  elements.btnExplainPlan.addEventListener("click", runExplainPlan);

  // Sandbox SQL Execution
  elements.btnRunSandbox.addEventListener("click", runSandboxSql);

  // Theme Toggle
  elements.btnThemeToggle.addEventListener("click", toggleTheme);

  // Trace Details Toggle
  elements.btnToggleTrace.addEventListener("click", () => {
    elements.retryTimeline.classList.toggle("hidden");
    elements.btnToggleTrace.textContent = elements.retryTimeline.classList.contains("hidden") 
      ? "View Trace Details" : "Hide Trace Details";
  });

  // Modals Open/Close
  elements.btnInspectSchema.addEventListener("click", openSchemaModal);
  elements.btnCloseSchema.addEventListener("click", () => elements.modalSchema.classList.add("hidden"));

  elements.btnOpenSettings.addEventListener("click", openSettingsModal);
  elements.btnCloseSettings.addEventListener("click", () => elements.modalSettings.classList.add("hidden"));
  elements.btnSaveSettings.addEventListener("click", handleSaveSettings);

  elements.btnOpenUpload.addEventListener("click", () => elements.modalUpload.classList.remove("hidden"));
  elements.btnCloseUpload.addEventListener("click", () => elements.modalUpload.classList.add("hidden"));

  // Close modals on overlay click
  [elements.modalSchema, elements.modalSettings, elements.modalUpload].forEach(m => {
    m.addEventListener("click", (e) => {
      if (e.target === m) m.classList.add("hidden");
    });
  });

  // Upload Tabs
  elements.uploadTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      elements.uploadTabs.forEach(t => t.classList.remove("active"));
      elements.uploadPanes.forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(tab.dataset.utab).classList.add("active");
    });
  });

  // Settings Max Retries Slider
  elements.settingMaxRetries.addEventListener("input", (e) => {
    elements.maxRetriesVal.textContent = e.target.value;
  });

  // API Key Visibility Toggle
  elements.btnToggleKeyVis.addEventListener("click", () => {
    if (elements.settingApiKey.type === "password") {
      elements.settingApiKey.type = "text";
      elements.btnToggleKeyVis.textContent = "Hide";
    } else {
      elements.settingApiKey.type = "password";
      elements.btnToggleKeyVis.textContent = "Show";
    }
  });

  // DB Drop Zone
  elements.dbDropZone.addEventListener("click", () => elements.dbFileInput.click());
  elements.dbFileInput.addEventListener("change", handleDbFileUpload);

  // CSV Drop Zone
  elements.csvDropZone.addEventListener("click", () => elements.csvFileInput.click());
  elements.csvFileInput.addEventListener("change", handleCsvFileUpload);

  // Confirm Reset
  elements.btnConfirmReset.addEventListener("click", handleResetDatabases);
}

// Toggle Dark / Light Theme
function toggleTheme() {
  state.isDarkTheme = !state.isDarkTheme;
  if (state.isDarkTheme) {
    document.body.classList.replace("light-theme", "dark-theme");
    localStorage.setItem("t2sql_theme", "dark");
  } else {
    document.body.classList.replace("dark-theme", "light-theme");
    localStorage.setItem("t2sql_theme", "light");
  }
  lucide.createIcons();
}

// Fetch Databases
async function loadDatabases() {
  try {
    const res = await fetch("/api/databases");
    const data = await res.json();
    state.databases = data.databases || [];
    state.activeDb = data.active_db || "ecommerce.db";

    elements.dbSelect.innerHTML = "";
    state.databases.forEach(db => {
      const opt = document.createElement("option");
      opt.value = db.filename;
      opt.textContent = `${db.name} (${db.filename})`;
      if (db.filename === state.activeDb) opt.selected = true;
      elements.dbSelect.appendChild(opt);
    });
  } catch (err) {
    console.error("Failed to load databases", err);
  }
}

// Fetch Sample Prompts
async function loadPrompts() {
  try {
    const res = await fetch("/api/prompts");
    state.prompts = await res.json();
  } catch (err) {
    console.error("Failed to load prompts", err);
  }
}

// Render Suggestion Chips
function renderPromptChips() {
  elements.promptChipsContainer.innerHTML = "";
  const list = state.prompts[state.activeDb] || [
    { label: "Top Customers", prompt: "Show top 5 customers by total spending" },
    { label: "Order Revenue", prompt: "Show order counts and total revenue grouped by status" }
  ];

  list.forEach(item => {
    const btn = document.createElement("button");
    btn.className = "chip-btn";
    btn.textContent = item.label;
    btn.title = item.prompt;
    btn.addEventListener("click", () => {
      elements.queryInput.value = item.prompt;
      executeNaturalQuery();
    });
    elements.promptChipsContainer.appendChild(btn);
  });
}

// Run Natural Language Analysis
async function executeNaturalQuery() {
  const question = elements.queryInput.value.trim();
  if (!question) {
    showToast("Please enter a question in plain English.", "error");
    elements.queryInput.focus();
    return;
  }

  // Update UI to running state
  elements.btnExecuteQuery.disabled = true;
  elements.btnExecuteQuery.innerHTML = `<span class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block"></span> <span>Analyzing...</span>`;
  elements.welcomeSection.classList.add("hidden");
  elements.retryLoopSection.classList.remove("hidden");
  elements.retryTimeline.classList.remove("hidden");
  elements.btnToggleTrace.textContent = "Hide Trace Details";

  elements.loopDot.className = "status-indicator-dot running";
  elements.loopTitle.textContent = "AI Agent Generating SQL & Validating Against Schema...";
  elements.attemptBadge.textContent = "Attempt 1 in progress";
  elements.retryTimeline.innerHTML = `
    <div class="attempt-card">
      <div class="attempt-card-header">
        <span class="attempt-num-tag" style="color:var(--amber)"><i data-lucide="loader" class="icon-xs"></i> Formulating initial query...</span>
      </div>
      <p style="font-size:0.8rem;color:var(--text-dim)">Examining table structures, column mappings, and dialect constraints.</p>
    </div>
  `;
  lucide.createIcons();

  const payload = {
    question: question,
    db_name: state.activeDb,
    provider: state.aiSettings.provider,
    api_key: state.aiSettings.apiKey || null,
    model: state.aiSettings.model || null,
    base_url: state.aiSettings.baseUrl || null,
    simulate_error: state.simulateError,
    max_retries: parseInt(state.aiSettings.maxRetries) || 3
  };

  try {
    const res = await fetch("/api/query/natural", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || "Query analysis failed");
    }

    const data = await res.json();
    state.lastAnalysis = data;
    renderAnalysisResults(data);

    // If simulation was enabled, reset toggle so subsequent runs run normally
    if (state.simulateError) {
      state.simulateError = false;
      elements.simulateErrorToggle.checked = false;
    }

  } catch (err) {
    elements.loopDot.className = "status-indicator-dot failed";
    elements.loopTitle.textContent = "Pipeline Failed";
    showToast(err.message, "error");
  } finally {
    elements.btnExecuteQuery.disabled = false;
    elements.btnExecuteQuery.innerHTML = `<i data-lucide="play" class="icon-sm"></i> <span>Analyze</span> <kbd class="key-hint">Enter</kbd>`;
    lucide.createIcons();
  }
}

// Render Results & Self-Healing Trace
function renderAnalysisResults(data) {
  // 1. Render Live Loop Pipeline Card
  const totalAttempts = data.total_attempts;
  const hadRetry = data.had_retry;

  elements.loopDot.className = data.success ? "status-indicator-dot" : "status-indicator-dot failed";
  elements.loopTitle.textContent = data.success
    ? (hadRetry ? `Self-Healing Succeeded! (Resolved on Attempt ${totalAttempts})` : `Query Verified & Executed on First Attempt`)
    : "Max Retries Reached - Query Failed";

  elements.attemptBadge.textContent = `${totalAttempts} Attempt${totalAttempts > 1 ? "s" : ""}`;
  elements.attemptBadge.style.color = hadRetry ? "var(--amber)" : "var(--emerald)";
  elements.loopDuration.innerHTML = `<i data-lucide="timer" class="icon-xs"></i> ${data.total_duration_ms}ms total`;

  // Render retry timeline steps
  elements.retryTimeline.innerHTML = "";
  data.retry_trace.forEach((step, idx) => {
    const card = document.createElement("div");
    card.className = `attempt-card ${step.status === "success" ? "attempt-success" : "attempt-failed"}`;
    
    let html = `
      <div class="attempt-card-header">
        <span class="attempt-num-tag">
          ${step.status === "success" 
            ? `<i data-lucide="check-circle" class="icon-xs"></i> Attempt ${step.attempt}: SUCCESS` 
            : `<i data-lucide="x-circle" class="icon-xs"></i> Attempt ${step.attempt}: EXECUTION ERROR`}
        </span>
        <span class="attempt-duration">${step.duration_ms}ms</span>
      </div>
      <div class="attempt-query-preview">${escapeHtml(step.query)}</div>
    `;

    if (step.status === "failed") {
      html += `
        <div class="attempt-error-box">
          <i data-lucide="alert-circle" class="icon-xs"></i>
          <div><strong>SQLite Error:</strong> ${escapeHtml(step.error)}</div>
        </div>
        <div class="self-heal-callout">
          <i data-lucide="refresh-cw" class="icon-xs"></i>
          <div><strong>Self-Correction Agent Activated:</strong> Error traceback and query fed back to LLM to rewrite and fix SQL.</div>
        </div>
      `;
    } else {
      html += `
        <div style="margin-top:6px;font-size:0.75rem;color:var(--emerald)">
          &check; Validated result set: <strong>${step.rows_count} rows</strong> returned.
        </div>
      `;
    }

    card.innerHTML = html;
    elements.retryTimeline.appendChild(card);
  });

  // 2. Render Results Section
  elements.resultsSection.classList.remove("hidden");

  // Overview Tab
  elements.questionEcho.textContent = data.question;
  elements.answerText.innerHTML = renderMarkdown(data.answer);

  // Meta pills
  elements.answerPills.innerHTML = `
    <span class="pill-item success"><i data-lucide="check" class="icon-xs"></i> ${data.success ? 'Success' : 'Failed'}</span>
    <span class="pill-item ${hadRetry ? 'retried' : ''}"><i data-lucide="refresh-cw" class="icon-xs"></i> ${totalAttempts} Attempt${totalAttempts > 1 ? 's' : ''}</span>
    <span class="pill-item"><i data-lucide="zap" class="icon-xs"></i> ${data.execution_time_ms}ms query execution</span>
    <span class="pill-item"><i data-lucide="database" class="icon-xs"></i> ${data.database}</span>
  `;

  // SQL Overview Code snippet
  elements.overviewSqlCode.textContent = data.query_used;
  Prism.highlightElement(elements.overviewSqlCode);

  // Full SQL Tab
  elements.fullSqlCode.textContent = data.query_used;
  Prism.highlightElement(elements.fullSqlCode);
  elements.sqlTimeTag.innerHTML = `<i data-lucide="zap" class="icon-xs"></i> ${data.execution_time_ms} ms`;
  elements.explainPlanContainer.classList.add("hidden");

  // Populate Sandbox
  elements.sandboxTextarea.value = data.query_used;

  // 3. Render Data Table
  renderDataTable(data.columns, data.rows, data.total_rows);

  // 4. Render Chart
  if (data.chart_data && data.chart_data.datasets && data.chart_data.datasets.length > 0) {
    elements.noChartMsg.classList.add("hidden");
    elements.analyticsChart.classList.remove("hidden");
    state.activeChartType = data.chart_data.type || "bar";
    
    // Set active button
    elements.chartTypeBtns.forEach(b => {
      b.classList.toggle("active", b.dataset.chart === state.activeChartType);
    });

    renderChart(data.chart_data, state.activeChartType);
  } else {
    elements.noChartMsg.classList.remove("hidden");
    elements.analyticsChart.classList.add("hidden");
    if (state.currentChart) {
      state.currentChart.destroy();
      state.currentChart = null;
    }
  }

  // Auto switch to overview tab
  const overviewBtn = document.querySelector('[data-tab="tab-overview"]');
  if (overviewBtn) overviewBtn.click();

  lucide.createIcons();
}

// Render Data Table
function renderDataTable(columns, rows, totalRows) {
  elements.resultRowCount.textContent = totalRows;
  elements.tableStats.textContent = `Showing ${rows.length} of ${totalRows} rows`;

  elements.tableHead.innerHTML = "";
  elements.tableBody.innerHTML = "";

  if (!columns || columns.length === 0) {
    elements.tableHead.innerHTML = `<tr><th>No Columns</th></tr>`;
    elements.tableBody.innerHTML = `<tr><td style="text-align:center;color:var(--text-dim)">No data returned</td></tr>`;
    return;
  }

  // Header
  const trHead = document.createElement("tr");
  columns.forEach(col => {
    const th = document.createElement("th");
    th.textContent = col;
    trHead.appendChild(th);
  });
  elements.tableHead.appendChild(trHead);

  // Rows
  rows.forEach(r => {
    const tr = document.createElement("tr");
    columns.forEach(col => {
      const td = document.createElement("td");
      const val = r[col];
      if (val === null || val === undefined) {
        td.innerHTML = `<span style="color:var(--text-dim);font-style:italic">NULL</span>`;
      } else if (typeof val === "number") {
        td.textContent = Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
      } else {
        td.textContent = String(val);
      }
      tr.appendChild(td);
    });
    elements.tableBody.appendChild(tr);
  });
}

// In-table Search Filter
function filterTableRows() {
  const query = elements.tableSearch.value.toLowerCase();
  const trs = elements.tableBody.querySelectorAll("tr");
  let visibleCount = 0;

  trs.forEach(tr => {
    const text = tr.textContent.toLowerCase();
    const match = text.includes(query);
    tr.style.display = match ? "" : "none";
    if (match) visibleCount++;
  });

  elements.tableStats.textContent = `Filtered ${visibleCount} row${visibleCount === 1 ? '' : 's'}`;
}

// Render Chart with Chart.js
function renderChart(chartConfig, chartType = "bar") {
  if (state.currentChart) {
    state.currentChart.destroy();
    state.currentChart = null;
  }

  const ctx = elements.analyticsChart.getContext("2d");
  const isDark = state.isDarkTheme;

  const textColor = isDark ? "#94a3b8" : "#475569";
  const gridColor = isDark ? "rgba(255, 255, 255, 0.06)" : "rgba(0, 0, 0, 0.06)";

  state.currentChart = new Chart(ctx, {
    type: chartType,
    data: {
      labels: chartConfig.labels,
      datasets: chartConfig.datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: { color: textColor, font: { family: "Plus Jakarta Sans", size: 12 } }
        },
        tooltip: {
          backgroundColor: "#0f172a",
          titleColor: "#f8fafc",
          bodyColor: "#cbd5e1",
          borderColor: "rgba(255, 255, 255, 0.1)",
          borderWidth: 1,
          padding: 10,
          cornerRadius: 8
        }
      },
      scales: chartType === "doughnut" ? {} : {
        x: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: "Plus Jakarta Sans", size: 11 } }
        },
        y: {
          grid: { color: gridColor },
          ticks: { color: textColor, font: { family: "Plus Jakarta Sans", size: 11 } }
        }
      }
    }
  });
}

// Run EXPLAIN QUERY PLAN
async function runExplainPlan() {
  if (!state.lastAnalysis || !state.lastAnalysis.query_used) return;

  try {
    elements.explainPlanContainer.classList.remove("hidden");
    elements.explainPlanOutput.textContent = "Analyzing query execution plan...";

    const res = await fetch("/api/query/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: state.lastAnalysis.query_used,
        db_name: state.activeDb
      })
    });
    const data = await res.json();
    if (data.success && data.rows) {
      const lines = data.rows.map(r => `[ID: ${r.id}, Parent: ${r.parent}] ${r.detail}`).join("\n");
      elements.explainPlanOutput.textContent = lines || "No execution plan steps returned.";
    } else {
      elements.explainPlanOutput.textContent = `Explain Plan Error: ${data.error}`;
    }
  } catch (err) {
    elements.explainPlanOutput.textContent = `Explain Error: ${err.message}`;
  }
}

// Run Sandbox SQL
async function runSandboxSql() {
  const sql = elements.sandboxTextarea.value.trim();
  if (!sql) {
    showToast("Please enter a SQL statement in the sandbox", "error");
    return;
  }

  elements.btnRunSandbox.disabled = true;
  elements.sandboxResultArea.classList.remove("hidden");
  elements.sandboxResultArea.innerHTML = `<div class="loading-spinner-wrapper"><div class="spinner"></div></div>`;

  try {
    const res = await fetch("/api/query/sql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: sql,
        db_name: state.activeDb
      })
    });

    const data = await res.json();
    if (data.success) {
      let tableHtml = `
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:0.8rem;color:var(--emerald)">
          <span>&check; Executed in ${data.execution_time_ms}ms</span>
          <span>${data.total_rows} rows</span>
        </div>
        <div class="table-scroll-container">
          <table class="data-table">
            <thead><tr>${data.columns.map(c => `<th>${c}</th>`).join("")}</tr></thead>
            <tbody>
              ${data.rows.map(r => `<tr>${data.columns.map(c => `<td>${r[c] !== null ? r[c] : 'NULL'}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>
      `;
      elements.sandboxResultArea.innerHTML = tableHtml;
    } else {
      elements.sandboxResultArea.innerHTML = `
        <div class="attempt-error-box">
          <i data-lucide="alert-circle" class="icon-xs"></i>
          <div><strong>Execution Error:</strong> ${escapeHtml(data.error)}</div>
        </div>
      `;
      lucide.createIcons();
    }
  } catch (err) {
    elements.sandboxResultArea.innerHTML = `<div class="attempt-error-box"><div>${escapeHtml(err.message)}</div></div>`;
  } finally {
    elements.btnRunSandbox.disabled = false;
  }
}

// Open Schema Modal
async function openSchemaModal() {
  elements.modalSchema.classList.remove("hidden");
  elements.schemaModalTitle.textContent = `Schema Inspector: ${state.activeDb}`;
  elements.schemaModalBody.innerHTML = `<div class="loading-spinner-wrapper"><div class="spinner"></div></div>`;

  try {
    const res = await fetch(`/api/schema?db_name=${state.activeDb}`);
    const data = await res.json();

    if (!data.tables || data.tables.length === 0) {
      elements.schemaModalBody.innerHTML = `<p style="color:var(--text-dim);text-align:center">No tables found in this database.</p>`;
      return;
    }

    let html = `<div class="schema-tables-grid">`;
    data.tables.forEach(tbl => {
      html += `
        <div class="schema-table-card">
          <div class="schema-table-header">
            <span class="schema-table-name">
              <i data-lucide="table" class="icon-sm"></i>
              ${tbl.table_name}
            </span>
            <span class="schema-table-count">~${tbl.row_count} rows &bull; ${tbl.columns.length} columns</span>
          </div>
          <div class="schema-columns-list">
            ${tbl.columns.map(c => `
              <div class="schema-col-item">
                <span class="schema-col-name">
                  ${c.name}
                  ${c.pk ? '<span class="pk-marker">PK</span>' : ''}
                </span>
                <span class="schema-col-type">${c.type}</span>
              </div>
            `).join("")}
          </div>
        </div>
      `;
    });
    html += `</div>`;
    elements.schemaModalBody.innerHTML = html;
    lucide.createIcons();
  } catch (err) {
    elements.schemaModalBody.innerHTML = `<p style="color:var(--rose)">Failed to inspect schema: ${err.message}</p>`;
  }
}

// Settings Modal
function openSettingsModal() {
  elements.modalSettings.classList.remove("hidden");
  elements.settingProvider.value = state.aiSettings.provider || "offline";
  elements.settingApiKey.value = state.aiSettings.apiKey || "";
  elements.settingModel.value = state.aiSettings.model || "";
  elements.settingBaseUrl.value = state.aiSettings.baseUrl || "";
  elements.settingMaxRetries.value = state.aiSettings.maxRetries || 3;
  elements.maxRetriesVal.textContent = state.aiSettings.maxRetries || 3;
}

function handleSaveSettings() {
  state.aiSettings.provider = elements.settingProvider.value;
  state.aiSettings.apiKey = elements.settingApiKey.value.trim();
  state.aiSettings.model = elements.settingModel.value.trim();
  state.aiSettings.baseUrl = elements.settingBaseUrl.value.trim();
  state.aiSettings.maxRetries = parseInt(elements.settingMaxRetries.value);
  saveSettings();
  elements.modalSettings.classList.add("hidden");
  showToast("AI preferences saved successfully!", "success");
}

// File Upload Handlers
async function handleDbFileUpload(e) {
  const file = e.target.files[0];
  if (!file) return;

  elements.dbUploadStatus.innerHTML = `<span style="color:var(--primary)">Uploading ${file.name}...</span>`;
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/upload/db", { method: "POST", body: formData });
    const data = await res.json();
    if (res.ok) {
      elements.dbUploadStatus.innerHTML = `<span style="color:var(--emerald)">&check; ${data.message}</span>`;
      await loadDatabases();
      showToast(`Loaded ${data.active_db}!`, "success");
      setTimeout(() => elements.modalUpload.classList.add("hidden"), 1200);
    } else {
      elements.dbUploadStatus.innerHTML = `<span style="color:var(--rose)">Error: ${data.detail}</span>`;
    }
  } catch (err) {
    elements.dbUploadStatus.innerHTML = `<span style="color:var(--rose)">Upload error: ${err.message}</span>`;
  }
}

async function handleCsvFileUpload(e) {
  const file = e.target.files[0];
  const tblName = elements.csvTableName.value.trim() || file.name.replace(".csv", "").replace(/[^a-zA-Z0-9_]/g, "_");
  if (!file) return;

  elements.csvUploadStatus.innerHTML = `<span style="color:var(--primary)">Converting ${file.name} to table '${tblName}'...</span>`;
  const formData = new FormData();
  formData.append("file", file);
  formData.append("table_name", tblName);
  formData.append("db_name", state.activeDb);

  try {
    const res = await fetch("/api/upload/csv", { method: "POST", body: formData });
    const data = await res.json();
    if (res.ok) {
      elements.csvUploadStatus.innerHTML = `<span style="color:var(--emerald)">&check; ${data.message}</span>`;
      showToast(data.message, "success");
      setTimeout(() => elements.modalUpload.classList.add("hidden"), 1200);
    } else {
      elements.csvUploadStatus.innerHTML = `<span style="color:var(--rose)">Error: ${data.detail}</span>`;
    }
  } catch (err) {
    elements.csvUploadStatus.innerHTML = `<span style="color:var(--rose)">CSV error: ${err.message}</span>`;
  }
}

// Reset Databases
async function handleResetDatabases() {
  if (!confirm("Are you sure you want to reset all sample databases to their original seed data?")) return;
  try {
    const res = await fetch("/api/databases/reset", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast("Databases reset to initial clean state!", "success");
      await loadDatabases();
      elements.modalUpload.classList.add("hidden");
    }
  } catch (err) {
    showToast("Reset failed: " + err.message, "error");
  }
}

// Export Results to CSV
function exportResultsToCsv() {
  if (!state.lastAnalysis || !state.lastAnalysis.rows || state.lastAnalysis.rows.length === 0) {
    showToast("No data rows available to export", "error");
    return;
  }

  const cols = state.lastAnalysis.columns;
  const rows = state.lastAnalysis.rows;
  
  let csvContent = "data:text/csv;charset=utf-8," + cols.join(",") + "\n";
  rows.forEach(r => {
    const rowVals = cols.map(c => {
      let val = r[c] !== null && r[c] !== undefined ? String(r[c]) : "";
      if (val.includes(",") || val.includes("\"") || val.includes("\n")) {
        val = `"${val.replace(/"/g, '""')}"`;
      }
      return val;
    });
    csvContent += rowVals.join(",") + "\n";
  });

  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `sql_analyst_export_${Date.now()}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  showToast("CSV downloaded successfully!", "success");
}

// Helper: Toast Notifications
function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <i data-lucide="${type === 'success' ? 'check-circle' : type === 'error' ? 'alert-triangle' : 'info'}" class="icon-sm"></i>
    <span>${escapeHtml(message)}</span>
  `;
  elements.toastContainer.appendChild(toast);
  lucide.createIcons();

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(30px)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Simple Markdown parser for highlights
function renderMarkdown(text) {
  if (!text) return "";
  let html = escapeHtml(text);
  // Bold **word**
  html = html.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
  // Italic *word*
  html = html.replace(/\*(.*?)\*/g, "<em>$1</em>");
  // Inline code `code`
  html = html.replace(/`(.*?)`/g, "<code style='background:rgba(255,255,255,0.1);padding:2px 6px;border-radius:4px;font-family:var(--font-mono);font-size:0.85em'>$1</code>");
  return html;
}

function escapeHtml(string) {
  if (!string) return "";
  return String(string)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Boot
document.addEventListener("DOMContentLoaded", init);
