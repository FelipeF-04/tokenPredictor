const STORAGE_KEYS = {
  sessionTokens: "aiUsageSessionTokens",
  sessionMap: "aiUsageSessionByConversation",
  activeSession: "aiUsageActiveSessionId",
  modelProfile: "aiUsageModelProfile",
};

const OPTIMIZE_DEBOUNCE_MS = 500;
const DEFAULT_STRATEGY = "auto";
const DEFAULT_RETRIEVAL_MODE = "embedding";
const DEFAULT_EMBEDDING_PROVIDER = "sentence-transformers";
const DEFAULT_EMBEDDING_MODEL = "bge-small-en";
const MAX_HISTORY_MESSAGES = 16;
const MAX_PREVIEW_CHARS = 3000;

const DEFAULT_CONFIG = {
  backend_base_url: "http://localhost:5000",
  default_model_profile: "gpt-4o-mini",
  token_window: 8000,
  risk_thresholds: { yellow: 0.6, red: 0.85 },
  debug: { dom: false },
};

let activeInput = null;
let analysisState = null;
let debounceId = null;
let lastCommittedText = "";
let ui = null;
let previewVisible = false;
let sessionId = null;
let selectedModelProfile = null;
let config = DEFAULT_CONFIG;
let domObserver = null;
let domFailures = 0;
let currentConversationKey = null;

function logDebug(message, details) {
  if (config?.debug?.dom) {
    // eslint-disable-next-line no-console
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

async function loadConfig() {
  const response = await AIUsageAPI.getConfig();
  if (response && response.success) {
    config = response.data;
    return config;
  }
  config = DEFAULT_CONFIG;
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
    await resolveSessionId();
    analysisState = null;
    lastCommittedText = "";
    setWidgetHidden();
  }
}

function ensureWidget() {
  if (ui) {
    return ui;
  }

  const widget = document.createElement("div");
  widget.id = "ai-usage-widget";
  widget.className = "ai-usage-widget ai-usage-hidden";
  widget.innerHTML = `
    <div class="ai-usage-title">Context Optimization</div>
    <div class="ai-usage-model" id="ai-usage-model">Model: -</div>
    <div class="ai-usage-row"><span>Original</span><span id="ai-usage-original">-</span></div>
    <div class="ai-usage-row"><span>Optimized</span><span id="ai-usage-optimized">-</span></div>
    <div class="ai-usage-row"><span>Savings</span><span id="ai-usage-savings">-</span></div>
    <div class="ai-usage-row"><span>Chunks kept</span><span id="ai-usage-chunks">-</span></div>
    <div class="ai-usage-badge ai-usage-badge--green" id="ai-usage-confidence">confidence</div>
    <button class="ai-usage-toggle" id="ai-usage-toggle" type="button">Show packed prompt</button>
    <button class="ai-usage-apply" id="ai-usage-apply" type="button" disabled>Apply optimized prompt</button>
    <div class="ai-usage-preview ai-usage-preview--hidden" id="ai-usage-preview">
      <div class="ai-usage-preview-title">Packed prompt</div>
      <pre class="ai-usage-preview-body" id="ai-usage-preview-body"></pre>
    </div>
    <div class="ai-usage-error" id="ai-usage-error"></div>
  `;

  document.body.appendChild(widget);

  ui = {
    widget,
    originalEl: widget.querySelector("#ai-usage-original"),
    optimizedEl: widget.querySelector("#ai-usage-optimized"),
    savingsEl: widget.querySelector("#ai-usage-savings"),
    chunksEl: widget.querySelector("#ai-usage-chunks"),
    badgeEl: widget.querySelector("#ai-usage-confidence"),
    modelEl: widget.querySelector("#ai-usage-model"),
    toggleEl: widget.querySelector("#ai-usage-toggle"),
    previewEl: widget.querySelector("#ai-usage-preview"),
    previewBodyEl: widget.querySelector("#ai-usage-preview-body"),
    errorEl: widget.querySelector("#ai-usage-error"),
    applyEl: widget.querySelector("#ai-usage-apply"),
  };

  ui.toggleEl.addEventListener("click", () => {
    previewVisible = !previewVisible;
    ui.previewEl.classList.toggle("ai-usage-preview--hidden", !previewVisible);
    ui.toggleEl.textContent = previewVisible ? "Hide packed prompt" : "Show packed prompt";
    positionWidget(activeInput);
  });

  ui.applyEl.addEventListener("click", () => {
    if (!analysisState || !analysisState.packed_prompt_text) {
      return;
    }
    if (!activeInput) {
      return;
    }
    AIUsageDomExtractors.setInputValue(activeInput, analysisState.packed_prompt_text);
    scheduleOptimize(analysisState.packed_prompt_text);
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

  const left = window.scrollX + rect.left;
  widget.style.top = `${top}px`;
  widget.style.left = `${left}px`;
}

function setWidgetError(message) {
  const { widget, errorEl } = ensureWidget();
  errorEl.textContent = message;
  widget.classList.remove("ai-usage-hidden");
}

function setWidgetHidden() {
  const { widget, errorEl } = ensureWidget();
  errorEl.textContent = "";
  widget.classList.add("ai-usage-hidden");
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

function formatCount(value) {
  if (Number.isFinite(value)) {
    return value;
  }
  return "-";
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

  const parts = renderedPrompt.map((item) => {
    const role = (item.role || "unknown").toUpperCase();
    const content = (item.content || "").trim();
    return `${role}:\n${content}`;
  });

  return parts.join("\n\n");
}

function updateWidget(data) {
  const {
    widget,
    originalEl,
    optimizedEl,
    savingsEl,
    chunksEl,
    badgeEl,
    modelEl,
    applyEl,
    previewBodyEl,
    errorEl,
  } = ensureWidget();
  errorEl.textContent = "";

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
  const confidenceText = Number.isFinite(confidenceValue)
    ? `confidence ${Math.round(confidenceValue * 100)}%`
    : "confidence -";
  const packedPrompt = renderPackedPrompt(data?.optimized?.rendered_prompt);

  originalEl.textContent = formatCount(original);
  optimizedEl.textContent = formatCount(optimized);
  savingsEl.textContent = formatCount(savings);
  chunksEl.textContent = chunksText;
  modelEl.textContent = selectedModelProfile ? `Model: ${selectedModelProfile}` : "Model: -";
  const previewText = packedPrompt || "No packed prompt available yet.";
  previewBodyEl.textContent = clipText(previewText, MAX_PREVIEW_CHARS) || "";
  applyEl.disabled = !packedPrompt;

  const confidenceLevel = Number.isFinite(confidenceValue)
    ? getConfidenceLevel(confidenceValue)
    : "green";
  badgeEl.textContent = confidenceText;
  badgeEl.classList.remove("ai-usage-badge--green", "ai-usage-badge--yellow", "ai-usage-badge--red");
  badgeEl.classList.add(`ai-usage-badge--${confidenceLevel}`);

  widget.classList.remove(
    "ai-usage-widget--green",
    "ai-usage-widget--yellow",
    "ai-usage-widget--red"
  );
  widget.classList.add(`ai-usage-widget--${confidenceLevel}`);

  widget.classList.remove("ai-usage-hidden");
  positionWidget(activeInput);
}

function collectConversationMessages(maxMessages) {
  return AIUsageDomExtractors.extractMessages(document, maxMessages);
}

async function optimizeMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) {
    analysisState = null;
    setWidgetHidden();
    return;
  }

  const historyMessages = collectConversationMessages(MAX_HISTORY_MESSAGES);
  const lastHistory = historyMessages[historyMessages.length - 1];
  if (!lastHistory || lastHistory.role !== "user" || lastHistory.content !== trimmed) {
    historyMessages.push({ role: "user", content: trimmed });
  }

  const response = await AIUsageAPI.optimize({
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

  if (response && response.success) {
    const data = response.data;
    const tokenCounts = data?.optimized?.token_counts || {};
    const packedPrompt = renderPackedPrompt(data?.optimized?.rendered_prompt);
    analysisState = {
      ...data,
      message: trimmed,
      original_tokens: Number(tokenCounts.original) || 0,
      optimized_tokens: Number(tokenCounts.optimized) || 0,
      packed_prompt_text: packedPrompt,
    };
    updateWidget(data);
  } else {
    analysisState = null;
    setWidgetError("Backend not reachable");
  }
}

function scheduleOptimize(message) {
  clearTimeout(debounceId);
  debounceId = setTimeout(() => optimizeMessage(message), OPTIMIZE_DEBOUNCE_MS);
}

function commitUsage() {
  if (!analysisState) {
    return;
  }

  const message = (analysisState.message || "").trim();
  if (!message || message === lastCommittedText) {
    return;
  }

  lastCommittedText = message;
  const deltaTokens = Number(analysisState.optimized_tokens || analysisState.original_tokens || 0);
  if (deltaTokens <= 0) {
    return;
  }
  storageGet([STORAGE_KEYS.sessionTokens])
    .then((result) => {
      const current = result[STORAGE_KEYS.sessionTokens] || {};
      const updated = {
        ...current,
        [sessionId]: (Number(current[sessionId]) || 0) + deltaTokens,
      };
      return storageSet({
        [STORAGE_KEYS.sessionTokens]: updated,
        [STORAGE_KEYS.activeSession]: sessionId,
      });
    })
    .catch(() => {});

  AIUsageAPI.commit(sessionId, deltaTokens, selectedModelProfile).catch(() => {});
}

function handleInputEvent(event) {
  const message = AIUsageDomExtractors.getInputValue(event.target);
  scheduleOptimize(message);
}

function handleKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    commitUsage();
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
    button.addEventListener("click", commitUsage);
  }
}

function ensureInput() {
  ensureConversationSession().catch(() => {});
  const inputElement = AIUsageDomExtractors.findInputElement(document);
  if (!inputElement) {
    setWidgetHidden();
    domFailures += 1;
    if (domObserver) {
      domObserver.notifyFailure();
    }
    if (domFailures > 8) {
      setWidgetError("Chat input not detected. Waiting for UI...");
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

function startObservers() {
  ensureWidget();
  ensureInput();
  hookSendButton();

  domObserver = AIUsageDomObservers.createObserver(() => {
    ensureInput();
    hookSendButton();
  });

  domObserver.observe(document.body);

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

async function init() {
  await loadConfig();
  await loadSelectedModel();
  await resolveSessionId();

  const { modelEl } = ensureWidget();
  if (modelEl) {
    modelEl.textContent = selectedModelProfile ? `Model: ${selectedModelProfile}` : "Model: -";
  }

  if (!AIUsageDomCompatibility.isSupportedHost(window.location)) {
    logDebug("Unsupported host", window.location.host);
    return;
  }

  startObservers();
}

chrome.storage.onChanged.addListener((changes) => {
  if (changes[STORAGE_KEYS.modelProfile]) {
    selectedModelProfile = changes[STORAGE_KEYS.modelProfile].newValue || config.default_model_profile;
    if (ui && ui.modelEl) {
      ui.modelEl.textContent = selectedModelProfile
        ? `Model: ${selectedModelProfile}`
        : "Model: -";
    }
  }
});

init();
