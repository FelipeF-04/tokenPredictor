const BACKEND_URL = "http://localhost:5000";
const STORAGE_KEY = "sessionTokens";
const OPTIMIZE_DEBOUNCE_MS = 500;
const DEFAULT_MODEL_PROFILE = "gpt-4o-mini";
const DEFAULT_STRATEGY = "auto";
const DEFAULT_RETRIEVAL_MODE = "embedding";
const DEFAULT_EMBEDDING_PROVIDER = "sentence-transformers";
const DEFAULT_EMBEDDING_MODEL = "bge-small-en";
const DEFAULT_OUTPUT_TOKENS = 1024;
const MAX_HISTORY_MESSAGES = 16;
const MAX_PREVIEW_CHARS = 3000;
const SESSION_ID = (() => {
  try {
    return crypto.randomUUID();
  } catch (error) {
    return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
})();

let activeInput = null;
let analysisState = null;
let debounceId = null;
let lastCommittedText = "";
let ui = null;
let previewVisible = false;

function isVisible(element) {
  if (!element) {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}

function getInputValue(element) {
  if (!element) {
    return "";
  }
  if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
    return element.value || "";
  }
  return element.textContent || "";
}

function findInputElement() {
  const textareas = Array.from(document.querySelectorAll("textarea")).filter(isVisible);
  if (textareas.length > 0) {
    return textareas[textareas.length - 1];
  }

  const editables = Array.from(
    document.querySelectorAll('[contenteditable="true"]')
  ).filter(isVisible);

  if (editables.length > 0) {
    return editables[editables.length - 1];
  }

  return null;
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
    setInputValue(activeInput, analysisState.packed_prompt_text);
    scheduleOptimize(analysisState.packed_prompt_text);
  });

  return ui;
}

function positionWidget(inputElement) {
  const { widget } = ensureWidget();
  if (!inputElement || !isVisible(inputElement)) {
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
  const nodes = Array.from(document.querySelectorAll("[data-message-author-role]"));
  const results = [];
  const seen = new Set();

  for (const node of nodes) {
    const role = (node.getAttribute("data-message-author-role") || "").trim();
    if (!role) {
      continue;
    }
    const content = (node.innerText || "").trim();
    if (!content) {
      continue;
    }
    const key = `${role}|${content}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    results.push({ role, content });
  }

  if (results.length > maxMessages) {
    return results.slice(-maxMessages);
  }
  return results;
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

  chrome.runtime.sendMessage(
    {
      action: "optimize",
      payload: {
        session_id: SESSION_ID,
        model_profile: DEFAULT_MODEL_PROFILE,
        strategy: DEFAULT_STRATEGY,
        embedding_provider: DEFAULT_EMBEDDING_PROVIDER,
        embedding_model: DEFAULT_EMBEDDING_MODEL,
        retrieval_mode: DEFAULT_RETRIEVAL_MODE,
        messages: historyMessages,
        options: {
          include_trace: false,
          include_removed_chunks: false,
          max_output_tokens: DEFAULT_OUTPUT_TOKENS,
        },
      },
    },
    (response) => {
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
  );
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

  chrome.storage.local.get([STORAGE_KEY], (result) => {
    const current = Number(result[STORAGE_KEY]) || 0;
    chrome.storage.local.set({ [STORAGE_KEY]: current + deltaTokens });
  });

  chrome.runtime.sendMessage(
    { action: "commit", delta_tokens: deltaTokens },
    () => {}
  );
}

function handleInputEvent(event) {
  const message = getInputValue(event.target);
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
  const button = document.querySelector(
    'button[aria-label*="Send"], button[data-testid="send-button"]'
  );

  if (button && !button.dataset.aiUsageAttached) {
    button.dataset.aiUsageAttached = "true";
    button.addEventListener("click", commitUsage);
  }
}

function ensureInput() {
  const inputElement = findInputElement();
  if (!inputElement) {
    setWidgetHidden();
    return;
  }

  activeInput = inputElement;
  attachToInput(inputElement);
  positionWidget(inputElement);
}

function startObservers() {
  ensureWidget();
  ensureInput();
  hookSendButton();

  const observer = new MutationObserver(() => {
    ensureInput();
    hookSendButton();
  });

  observer.observe(document.body, { childList: true, subtree: true });

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

startObservers();
