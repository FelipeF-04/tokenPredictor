const BACKEND_URL = "http://localhost:5000";
const STORAGE_KEY = "sessionTokens";
const ANALYZE_DEBOUNCE_MS = 400;

let activeInput = null;
let analysisState = null;
let debounceId = null;
let lastCommittedText = "";
let ui = null;

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
    <div class="ai-usage-title">AI Usage</div>
    <div class="ai-usage-row"><span>Input</span><span id="ai-usage-input">-</span></div>
    <div class="ai-usage-row"><span>Output</span><span id="ai-usage-output">-</span></div>
    <div class="ai-usage-row"><span>Total</span><span id="ai-usage-total">-</span></div>
    <div class="ai-usage-badge ai-usage-badge--green" id="ai-usage-risk">green</div>
    <div class="ai-usage-error" id="ai-usage-error"></div>
  `;

  document.body.appendChild(widget);

  ui = {
    widget,
    inputEl: widget.querySelector("#ai-usage-input"),
    outputEl: widget.querySelector("#ai-usage-output"),
    totalEl: widget.querySelector("#ai-usage-total"),
    riskEl: widget.querySelector("#ai-usage-risk"),
    errorEl: widget.querySelector("#ai-usage-error"),
  };

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

function updateWidget(data) {
  const { widget, inputEl, outputEl, totalEl, riskEl, errorEl } = ensureWidget();
  errorEl.textContent = "";

  inputEl.textContent = data.input_tokens;
  outputEl.textContent = data.predicted_output_tokens;
  totalEl.textContent = data.projected_total_tokens;

  const risk = data.risk_level || "green";
  riskEl.textContent = risk;
  riskEl.classList.remove("ai-usage-badge--green", "ai-usage-badge--yellow", "ai-usage-badge--red");
  riskEl.classList.add(`ai-usage-badge--${risk}`);

  widget.classList.remove(
    "ai-usage-widget--green",
    "ai-usage-widget--yellow",
    "ai-usage-widget--red"
  );
  widget.classList.add(`ai-usage-widget--${risk}`);

  widget.classList.remove("ai-usage-hidden");
  positionWidget(activeInput);
}

async function analyzeMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) {
    analysisState = null;
    setWidgetHidden();
    return;
  }

  chrome.runtime.sendMessage(
    { action: "analyze", message: trimmed },
    (response) => {
      if (response && response.success) {
        const data = response.data;
        analysisState = { ...data, message: trimmed };
        updateWidget(data);
      } else {
        analysisState = null;
        setWidgetError("Backend not reachable");
      }
    }
  );
}

function scheduleAnalyze(message) {
  clearTimeout(debounceId);
  debounceId = setTimeout(() => analyzeMessage(message), ANALYZE_DEBOUNCE_MS);
}

function commitUsage() {
  if (!analysisState || !analysisState.projected_total_tokens) {
    return;
  }

  const message = (analysisState.message || "").trim();
  if (!message || message === lastCommittedText) {
    return;
  }

  lastCommittedText = message;
  const deltaTokens = Number(analysisState.projected_total_tokens) || 0;
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
  scheduleAnalyze(message);
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
