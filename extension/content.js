const STORAGE_KEYS = {
  sessionTokens: "aiUsageSessionTokens",
  sessionMap: "aiUsageSessionByConversation",
  activeSession: "aiUsageActiveSessionId",
  modelProfile: "aiUsageModelProfile",
  ledgerQueue: "aiUsageLedgerQueue",
  ledgerStatus: "aiUsageLedgerStatus",
};

const ANALYZE_DEBOUNCE_MS = 300;
const DEFAULT_STRATEGY = "auto";
const DEFAULT_RETRIEVAL_MODE = "embedding";
const DEFAULT_EMBEDDING_PROVIDER = "sentence-transformers";
const DEFAULT_EMBEDDING_MODEL = "bge-small-en";
const MAX_HISTORY_MESSAGES = 16;
const MAX_PREVIEW_CHARS = 3000;
const ASSISTANT_STABILITY_MS = 2500;
const LEDGER_RETRY_MS = 15000;

const DEFAULT_CONFIG = {
  backend_base_url: "http://localhost:5000",
  default_model_profile: "gpt-4o-mini",
  token_window: 8000,
  risk_thresholds: { yellow: 0.6, red: 0.85 },
  debug: { dom: false },
};

let activeInput = null;
let optimizationState = null;
let optimizationMessage = "";
let actualSessionTotal = null;
let ui = null;
let previewVisible = false;
let sessionId = null;
let selectedModelProfile = null;
let config = DEFAULT_CONFIG;
let domObserver = null;
let domFailures = 0;
let currentConversationKey = null;
let contentController = null;
let conversationTracker = null;
let ledgerStatusState = { state: "synced", text: "Session synced", pendingCount: 0 };
let lastLedgerStatusSessionId = null;
let ledgerStatusWrite = Promise.resolve();

function logDebug(message, details) {
  if (config?.debug?.dom) {
    console.debug("[AI Usage Predictor]", message, details || "");
  }
}

function getConversationKey() {
  const host = window.location.host || "unknown";
  const path = window.location.pathname || "/";
  return `${host}${path}`;
}

function storageGet(keys) {
  return new Promise((resolve) => {
    chrome.storage.local.get(keys, (result) => resolve(result || {}));
  });
}

function storageSet(payload) {
  return new Promise((resolve) => {
    chrome.storage.local.set(payload, () => resolve());
  });
}

function updateActualSessionTotal(total, targetSessionId = sessionId) {
  const numeric = Number(total);
  if (!Number.isFinite(numeric)) {
    return;
  }
  if (ui?.actualEl && targetSessionId === sessionId) {
    actualSessionTotal = numeric;
    ui.actualEl.textContent = formatCount(numeric);
  }
}

async function persistCorrectedSessionTotal(data, payload) {
  const targetSessionId = data?.session_id || payload?.session_id;
  const total = Number(data?.corrected_session_total ?? data?.session_tokens);
  if (!targetSessionId || !Number.isFinite(total)) {
    return;
  }
  const stored = await storageGet([STORAGE_KEYS.sessionTokens]);
  const totals = stored[STORAGE_KEYS.sessionTokens] || {};
  await storageSet({
    [STORAGE_KEYS.sessionTokens]: { ...totals, [targetSessionId]: total },
    [STORAGE_KEYS.activeSession]: sessionId,
  });
  updateActualSessionTotal(total, targetSessionId);
}

async function loadCachedSessionTotal() {
  if (!sessionId) {
    return;
  }
  const stored = await storageGet([STORAGE_KEYS.sessionTokens]);
  const totals = stored[STORAGE_KEYS.sessionTokens] || {};
  if (Object.prototype.hasOwnProperty.call(totals, sessionId)) {
    updateActualSessionTotal(Number(totals[sessionId]) || 0);
  } else {
    actualSessionTotal = null;
    if (ui?.actualEl) {
      ui.actualEl.textContent = "0";
    }
  }
}

function updateLedgerStatus(status) {
  const nextStatus = status || {
    state: "synced",
    text: "Session synced",
    pendingCount: 0,
  };
  const changed =
    ledgerStatusState.state !== nextStatus.state ||
    ledgerStatusState.text !== nextStatus.text ||
    ledgerStatusState.pendingCount !== nextStatus.pendingCount ||
    lastLedgerStatusSessionId !== sessionId;
  ledgerStatusState = nextStatus;
  const { widget, syncStatusEl } = ensureWidget();
  syncStatusEl.textContent = ledgerStatusState.text;
  syncStatusEl.classList.remove(
    "ai-usage-sync-status--synced",
    "ai-usage-sync-status--waiting",
    "ai-usage-sync-status--queued"
  );
  syncStatusEl.classList.add(`ai-usage-sync-status--${ledgerStatusState.state}`);
  if (ledgerStatusState.state !== "synced") {
    widget.classList.remove("ai-usage-hidden");
    positionWidget(activeInput);
  }
  if (changed && sessionId) {
    const targetSessionId = sessionId;
    const statusSnapshot = { ...ledgerStatusState };
    lastLedgerStatusSessionId = targetSessionId;
    ledgerStatusWrite = ledgerStatusWrite
      .then(() => storageGet([STORAGE_KEYS.ledgerStatus]))
      .then((stored) => {
        const statuses = stored[STORAGE_KEYS.ledgerStatus] || {};
        return storageSet({
          [STORAGE_KEYS.ledgerStatus]: {
            ...statuses,
            [targetSessionId]: statusSnapshot,
          },
        });
      })
      .catch(() => {});
  }
}

async function loadConfig() {
  const response = await AIUsageAPI.getConfig();
  config = response && response.success ? response.data : DEFAULT_CONFIG;
  return config;
}

async function loadSelectedModel() {
  const stored = await storageGet([STORAGE_KEYS.modelProfile]);
  selectedModelProfile = stored[STORAGE_KEYS.modelProfile] || config.default_model_profile;
  return selectedModelProfile;
}

function buildSessionId() {
  try {
    return crypto.randomUUID();
  } catch (error) {
    return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

async function resolveSessionId() {
  const conversationKey = getConversationKey();
  const stored = await storageGet([STORAGE_KEYS.sessionMap, STORAGE_KEYS.activeSession]);
  const map = stored[STORAGE_KEYS.sessionMap] || {};
  let current = map[conversationKey];
  if (!current) {
    current = buildSessionId();
    map[conversationKey] = current;
  }
  await storageSet({
    [STORAGE_KEYS.sessionMap]: map,
    [STORAGE_KEYS.activeSession]: current,
  });
  sessionId = current;
  currentConversationKey = conversationKey;
  return current;
}

async function ensureConversationSession() {
  const conversationKey = getConversationKey();
  if (conversationKey !== currentConversationKey) {
    contentController.invalidateLive();
    await resolveSessionId();
    optimizationState = null;
    optimizationMessage = "";
    actualSessionTotal = null;
    await loadCachedSessionTotal();
    setWidgetHidden();
    return true;
  }
  return false;
}

function ensureWidget() {
  if (ui) {
    return ui;
  }

  const widget = document.createElement("aside");
  widget.id = "ai-usage-widget";
  widget.className = "ai-usage-widget ai-usage-hidden";
  widget.setAttribute("aria-label", "AI usage estimate");
  widget.innerHTML = `
    <div class="ai-usage-title">AI Usage Predictor</div>
    <div class="ai-usage-model" id="ai-usage-model">Model: -</div>
    <div class="ai-usage-section-title">Live draft estimate</div>
    <div class="ai-usage-row"><span>Input tokens</span><span id="ai-usage-input">-</span></div>
    <div class="ai-usage-row"><span>Estimated output</span><span id="ai-usage-output">-</span></div>
    <div class="ai-usage-row"><span>Projected total if sent</span><span id="ai-usage-projected">-</span></div>
    <div class="ai-usage-row"><span>Actual session total</span><span id="ai-usage-actual">0</span></div>
    <div class="ai-usage-row" id="ai-usage-available-row" hidden>
      <span>Available context</span><span id="ai-usage-available">-</span>
    </div>
    <div class="ai-usage-badge ai-usage-badge--green" id="ai-usage-risk" role="status" aria-live="polite">Risk: -</div>
    <div class="ai-usage-status" id="ai-usage-live-status" role="status" aria-live="polite"></div>
    <div class="ai-usage-sync-status" id="ai-usage-sync-status" role="status" aria-live="polite">Session synced</div>
    <button class="ai-usage-optimize" id="ai-usage-optimize" type="button" disabled>Optimize context</button>
    <div class="ai-usage-optimization" id="ai-usage-optimization" hidden>
      <div class="ai-usage-section-title">Context optimization</div>
      <div class="ai-usage-row"><span>Original</span><span id="ai-usage-original">-</span></div>
      <div class="ai-usage-row"><span>Optimized</span><span id="ai-usage-optimized">-</span></div>
      <div class="ai-usage-row"><span>Savings</span><span id="ai-usage-savings">-</span></div>
      <div class="ai-usage-row"><span>Chunks kept</span><span id="ai-usage-chunks">-</span></div>
      <div class="ai-usage-badge ai-usage-badge--green" id="ai-usage-confidence">Confidence: -</div>
      <button class="ai-usage-toggle" id="ai-usage-toggle" type="button">Show packed prompt</button>
      <button class="ai-usage-apply" id="ai-usage-apply" type="button" disabled>Apply optimized prompt</button>
      <div class="ai-usage-preview ai-usage-preview--hidden" id="ai-usage-preview">
        <div class="ai-usage-preview-title">Packed prompt</div>
        <pre class="ai-usage-preview-body" id="ai-usage-preview-body"></pre>
      </div>
    </div>
    <div class="ai-usage-error" id="ai-usage-optimization-error" role="status" aria-live="assertive"></div>
  `;

  document.body.appendChild(widget);

  ui = {
    widget,
    inputEl: widget.querySelector("#ai-usage-input"),
    outputEl: widget.querySelector("#ai-usage-output"),
    projectedEl: widget.querySelector("#ai-usage-projected"),
    actualEl: widget.querySelector("#ai-usage-actual"),
    availableRowEl: widget.querySelector("#ai-usage-available-row"),
    availableEl: widget.querySelector("#ai-usage-available"),
    riskEl: widget.querySelector("#ai-usage-risk"),
    liveStatusEl: widget.querySelector("#ai-usage-live-status"),
    syncStatusEl: widget.querySelector("#ai-usage-sync-status"),
    modelEl: widget.querySelector("#ai-usage-model"),
    optimizeEl: widget.querySelector("#ai-usage-optimize"),
    optimizationEl: widget.querySelector("#ai-usage-optimization"),
    originalEl: widget.querySelector("#ai-usage-original"),
    optimizedEl: widget.querySelector("#ai-usage-optimized"),
    savingsEl: widget.querySelector("#ai-usage-savings"),
    chunksEl: widget.querySelector("#ai-usage-chunks"),
    confidenceEl: widget.querySelector("#ai-usage-confidence"),
    toggleEl: widget.querySelector("#ai-usage-toggle"),
    previewEl: widget.querySelector("#ai-usage-preview"),
    previewBodyEl: widget.querySelector("#ai-usage-preview-body"),
    optimizationErrorEl: widget.querySelector("#ai-usage-optimization-error"),
    applyEl: widget.querySelector("#ai-usage-apply"),
  };

  ui.optimizeEl.addEventListener("click", requestOptimization);

  ui.toggleEl.addEventListener("click", () => {
    previewVisible = !previewVisible;
    ui.previewEl.classList.toggle("ai-usage-preview--hidden", !previewVisible);
    ui.toggleEl.textContent = previewVisible ? "Hide packed prompt" : "Show packed prompt";
    positionWidget(activeInput);
  });

  ui.applyEl.addEventListener("click", () => {
    if (!optimizationState?.packed_prompt_text || !activeInput) {
      return;
    }
    AIUsageDomExtractors.setInputValue(activeInput, optimizationState.packed_prompt_text);
    ui.liveStatusEl.textContent = "Optimized prompt applied. Updating estimate…";
  });

  return ui;
}

function positionWidget(inputElement) {
  const { widget } = ensureWidget();
  if (!inputElement || !AIUsageDomExtractors.isVisible(inputElement)) {
    widget.classList.add("ai-usage-hidden");
    return;
  }

  const rect = inputElement.getBoundingClientRect();
  const widgetRect = widget.getBoundingClientRect();
  let top = window.scrollY + rect.top - widgetRect.height - 10;
  if (top < window.scrollY + 10) {
    top = window.scrollY + rect.bottom + 10;
  }
  widget.style.top = `${top}px`;
  widget.style.left = `${window.scrollX + rect.left}px`;
}

function setWidgetHidden() {
  const { widget, liveStatusEl, optimizationErrorEl } = ensureWidget();
  liveStatusEl.textContent = "";
  optimizationErrorEl.textContent = "";
  if (ledgerStatusState.state !== "synced") {
    widget.classList.remove("ai-usage-hidden");
    positionWidget(activeInput);
    return;
  }
  widget.classList.add("ai-usage-hidden");
}

function setLiveError(message) {
  const { widget, liveStatusEl } = ensureWidget();
  liveStatusEl.textContent = message;
  widget.classList.remove("ai-usage-hidden");
  positionWidget(activeInput);
}

function formatCount(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? Math.max(Math.round(numeric), 0).toLocaleString() : "-";
}

function clipText(text, maxChars) {
  if (!text || text.length <= maxChars) {
    return text;
  }
  return `${text.slice(0, maxChars)}\n... (truncated)`;
}

function renderPackedPrompt(renderedPrompt) {
  if (!Array.isArray(renderedPrompt) || renderedPrompt.length === 0) {
    return "";
  }
  return renderedPrompt
    .map((item) => {
      const role = (item.role || "unknown").toUpperCase();
      const content = (item.content || "").trim();
      return `${role}:\n${content}`;
    })
    .join("\n\n");
}

function setWidgetRisk(level) {
  const normalized = ["green", "yellow", "red"].includes(level) ? level : "green";
  const { widget, riskEl } = ensureWidget();
  riskEl.textContent = `Risk: ${level || "-"}`;
  riskEl.classList.remove(
    "ai-usage-badge--green",
    "ai-usage-badge--yellow",
    "ai-usage-badge--red"
  );
  riskEl.classList.add(`ai-usage-badge--${normalized}`);
  widget.classList.remove(
    "ai-usage-widget--green",
    "ai-usage-widget--yellow",
    "ai-usage-widget--red"
  );
  widget.classList.add(`ai-usage-widget--${normalized}`);
}

function resetOptimizationPresentation() {
  if (!ui) {
    return;
  }
  optimizationState = null;
  previewVisible = false;
  ui.optimizationEl.hidden = true;
  ui.previewEl.classList.add("ai-usage-preview--hidden");
  ui.toggleEl.textContent = "Show packed prompt";
  ui.applyEl.disabled = true;
  ui.optimizationErrorEl.textContent = "";
}

function updateLiveWidget(data, message) {
  const {
    widget,
    inputEl,
    outputEl,
    projectedEl,
    actualEl,
    availableRowEl,
    availableEl,
    liveStatusEl,
    modelEl,
    optimizeEl,
  } = ensureWidget();

  if (optimizationMessage && optimizationMessage !== message) {
    optimizationMessage = "";
    resetOptimizationPresentation();
  }

  const sessionTokens = Number(data?.session_tokens);
  if (!Number.isFinite(actualSessionTotal) && Number.isFinite(sessionTokens)) {
    updateActualSessionTotal(sessionTokens);
  }
  const committedSessionTokens = Number.isFinite(actualSessionTotal)
    ? actualSessionTotal
    : Number.isFinite(sessionTokens)
      ? sessionTokens
      : 0;
  const projectedTokens = Number(data?.projected_total_tokens);
  const projectedSessionTotal =
    committedSessionTokens +
    (Number.isFinite(projectedTokens) ? projectedTokens : 0);
  const availableContext = Number(data?.available_context_tokens);

  inputEl.textContent = formatCount(data?.input_tokens);
  outputEl.textContent = formatCount(data?.predicted_output_tokens);
  projectedEl.textContent = formatCount(projectedSessionTotal);
  actualEl.textContent = formatCount(committedSessionTokens);
  availableRowEl.hidden = !Number.isFinite(availableContext);
  availableEl.textContent = formatCount(availableContext);
  modelEl.textContent = selectedModelProfile ? `Model: ${selectedModelProfile}` : "Model: -";
  liveStatusEl.textContent = "";
  optimizeEl.disabled = false;
  setWidgetRisk(data?.risk_level);
  widget.classList.remove("ai-usage-hidden");
  positionWidget(activeInput);
}

function getConfidenceLevel(confidence) {
  if (confidence >= 0.8) {
    return "green";
  }
  if (confidence >= 0.6) {
    return "yellow";
  }
  return "red";
}

function updateOptimizationWidget(data) {
  const {
    widget,
    optimizationEl,
    originalEl,
    optimizedEl,
    savingsEl,
    chunksEl,
    confidenceEl,
    previewBodyEl,
    optimizationErrorEl,
    applyEl,
  } = ensureWidget();
  const tokenCounts = data?.optimized?.token_counts || {};
  const original = Number(tokenCounts.original);
  const optimized = Number(tokenCounts.optimized);
  const savings = Number.isFinite(original) && Number.isFinite(optimized)
    ? Math.max(original - optimized, 0)
    : NaN;
  const confidenceValue = Number(data?.metrics?.confidence);
  const totalChunks = Number(data?.stats?.total_chunks);
  const keptChunks = Number(data?.stats?.kept_chunks);
  const chunksText = Number.isFinite(totalChunks) && totalChunks > 0
    ? `${keptChunks}/${totalChunks}`
    : "-";
  const packedPrompt = renderPackedPrompt(data?.optimized?.rendered_prompt);

  optimizationState = {
    ...data,
    message: optimizationMessage,
    packed_prompt_text: packedPrompt,
  };
  originalEl.textContent = formatCount(original);
  optimizedEl.textContent = formatCount(optimized);
  savingsEl.textContent = formatCount(savings);
  chunksEl.textContent = chunksText;
  previewBodyEl.textContent = clipText(
    packedPrompt || "No packed prompt available.",
    MAX_PREVIEW_CHARS
  );
  applyEl.disabled = !packedPrompt;
  optimizationErrorEl.textContent = "";
  optimizationEl.hidden = false;

  const confidenceLevel = Number.isFinite(confidenceValue)
    ? getConfidenceLevel(confidenceValue)
    : "green";
  confidenceEl.textContent = Number.isFinite(confidenceValue)
    ? `Confidence: ${Math.round(confidenceValue * 100)}%`
    : "Confidence: -";
  confidenceEl.classList.remove(
    "ai-usage-badge--green",
    "ai-usage-badge--yellow",
    "ai-usage-badge--red"
  );
  confidenceEl.classList.add(`ai-usage-badge--${confidenceLevel}`);
  widget.classList.remove("ai-usage-hidden");
  positionWidget(activeInput);
}

function setOptimizeLoading(running) {
  const { optimizeEl, optimizationErrorEl } = ensureWidget();
  optimizeEl.disabled = running;
  optimizeEl.textContent = running ? "Optimizing…" : "Optimize context";
  optimizeEl.setAttribute("aria-busy", running ? "true" : "false");
  if (running) {
    optimizationErrorEl.textContent = "Optimizing context…";
  }
  positionWidget(activeInput);
}

function collectConversationMessages(maxMessages) {
  return AIUsageDomExtractors.extractMessages(document, maxMessages);
}

async function requestOptimization() {
  const message = AIUsageDomExtractors.getInputValue(activeInput).trim();
  if (!message) {
    return;
  }

  optimizationMessage = message;
  const historyMessages = collectConversationMessages(MAX_HISTORY_MESSAGES);
  const lastHistory = historyMessages[historyMessages.length - 1];
  if (!lastHistory || lastHistory.role !== "user" || lastHistory.content !== message) {
    historyMessages.push({ role: "user", content: message });
  }

  await contentController.optimize({
    session_id: sessionId,
    model_profile: selectedModelProfile,
    strategy: DEFAULT_STRATEGY,
    embedding_provider: DEFAULT_EMBEDDING_PROVIDER,
    embedding_model: DEFAULT_EMBEDDING_MODEL,
    retrieval_mode: DEFAULT_RETRIEVAL_MODE,
    messages: historyMessages,
    options: {
      include_trace: false,
      include_removed_chunks: false,
    },
  });
}

function noteConversationSend() {
  if (conversationTracker) {
    conversationTracker.markWaiting();
  }
  setTimeout(() => {
    scanConversation().catch(() => {});
  }, 0);
}

async function scanConversation() {
  if (!conversationTracker || !sessionId) {
    return;
  }
  const events = AIUsageDomExtractors.extractMessageEvents(document);
  await conversationTracker.observe(events, {
    sessionId,
    modelProfile: selectedModelProfile,
  });
}

function handleInputEvent(event) {
  const message = AIUsageDomExtractors.getInputValue(event.target);
  contentController.scheduleAnalyze(message, {
    sessionId,
    modelProfile: selectedModelProfile,
  });
}

function handleKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    noteConversationSend();
  }
}

function attachToInput(element) {
  if (!element || element.dataset.aiUsageAttached) {
    return;
  }
  element.dataset.aiUsageAttached = "true";
  element.addEventListener("input", handleInputEvent);
  element.addEventListener("keydown", handleKeydown);
  element.addEventListener("focus", handleInputEvent);
}

function hookSendButton() {
  const button = AIUsageDomExtractors.findSendButton(document);
  if (button && !button.dataset.aiUsageAttached) {
    button.dataset.aiUsageAttached = "true";
    button.addEventListener("click", noteConversationSend);
  }
}

function ensureInput() {
  const inputElement = AIUsageDomExtractors.findInputElement(document);
  if (!inputElement) {
    setWidgetHidden();
    domFailures += 1;
    if (domObserver) {
      domObserver.notifyFailure();
    }
    if (domFailures > 8) {
      setLiveError("Chat input not detected. Waiting for UI…");
      logDebug("Input not found", AIUsageDomCompatibility.describe(document));
    }
    return;
  }

  activeInput = inputElement;
  attachToInput(inputElement);
  positionWidget(inputElement);
  domFailures = 0;
  if (domObserver) {
    domObserver.notifySuccess();
  }
  logDebug("Input attached", { host: window.location.host });
}

async function refreshPageState() {
  await ensureConversationSession();
  ensureInput();
  hookSendButton();
  await scanConversation();
}

function startObservers() {
  ensureWidget();
  refreshPageState().catch((error) => {
    logDebug("Initial conversation scan failed", error);
  });

  domObserver = AIUsageDomObservers.createObserver(() => {
    refreshPageState().catch((error) => {
      logDebug("Conversation scan failed", error);
    });
  });
  domObserver.observe(document.body);

  window.setInterval(() => {
    conversationTracker?.retryQueued().catch(() => {});
  }, LEDGER_RETRY_MS);
  window.addEventListener("online", () => {
    conversationTracker?.retryQueued().catch(() => {});
  });

  window.addEventListener(
    "scroll",
    () => {
      if (activeInput) {
        positionWidget(activeInput);
      }
    },
    { passive: true }
  );
  window.addEventListener("resize", () => {
    if (activeInput) {
      positionWidget(activeInput);
    }
  });
}

contentController = AIUsageContentController.create({
  api: AIUsageAPI,
  debounceMs: ANALYZE_DEBOUNCE_MS,
  onLiveSuccess(data, message) {
    updateLiveWidget(data, message);
  },
  onLiveError(error) {
    setLiveError(`Live estimate unavailable: ${error}`);
  },
  onLiveClear() {
    optimizationMessage = "";
    resetOptimizationPresentation();
    setWidgetHidden();
  },
  onOptimizeStart() {
    resetOptimizationPresentation();
    setOptimizeLoading(true);
  },
  onOptimizeSuccess(data) {
    setOptimizeLoading(false);
    updateOptimizationWidget(data);
  },
  onOptimizeError(error) {
    const { optimizationEl, optimizationErrorEl } = ensureWidget();
    setOptimizeLoading(false);
    optimizationEl.hidden = true;
    optimizationErrorEl.textContent = `Optimization unavailable: ${error}`;
    positionWidget(activeInput);
  },
});

conversationTracker = AIUsageConversationTracker.create({
  storage: {
    async load() {
      const stored = await storageGet([STORAGE_KEYS.ledgerQueue]);
      return stored[STORAGE_KEYS.ledgerQueue] || [];
    },
    async save(queue) {
      await storageSet({ [STORAGE_KEYS.ledgerQueue]: queue });
    },
  },
  recordEvent(payload) {
    return AIUsageAPI.recordEvent(payload);
  },
  stabilityMs: ASSISTANT_STABILITY_MS,
  onStatus(status) {
    updateLedgerStatus(status);
  },
  onRecorded(data, payload) {
    persistCorrectedSessionTotal(data, payload).catch(() => {});
  },
});

async function init() {
  await loadConfig();
  await loadSelectedModel();
  await resolveSessionId();

  const { modelEl } = ensureWidget();
  modelEl.textContent = selectedModelProfile ? `Model: ${selectedModelProfile}` : "Model: -";

  if (!AIUsageDomCompatibility.isSupportedHost(window.location)) {
    logDebug("Unsupported host", window.location.host);
    return;
  }
  await conversationTracker.initialize();
  await loadCachedSessionTotal();
  startObservers();
}

chrome.storage.onChanged.addListener((changes) => {
  if (changes[STORAGE_KEYS.sessionTokens] && sessionId) {
    const totals = changes[STORAGE_KEYS.sessionTokens].newValue || {};
    if (Object.prototype.hasOwnProperty.call(totals, sessionId)) {
      updateActualSessionTotal(Number(totals[sessionId]) || 0);
    }
  }
  if (changes[STORAGE_KEYS.modelProfile]) {
    selectedModelProfile = changes[STORAGE_KEYS.modelProfile].newValue || config.default_model_profile;
    if (ui?.modelEl) {
      ui.modelEl.textContent = selectedModelProfile
        ? `Model: ${selectedModelProfile}`
        : "Model: -";
    }
    if (activeInput) {
      handleInputEvent({ target: activeInput });
    }
  }
});

init();
