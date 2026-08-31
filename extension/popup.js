const STORAGE_KEYS = {
  sessionTokens: "aiUsageSessionTokens",
  activeSession: "aiUsageActiveSessionId",
  modelProfile: "aiUsageModelProfile",
  ledgerStatus: "aiUsageLedgerStatus",
};

const DEFAULT_CONFIG = {
  default_model_profile: "gpt-4o-mini",
  token_window: 8000,
  risk_thresholds: { yellow: 0.6, red: 0.85 },
};

const sessionTokensEl = document.getElementById("sessionTokens");
const riskFillEl = document.getElementById("riskFill");
const riskLabelEl = document.getElementById("riskLabel");
const resetBtn = document.getElementById("resetBtn");
const statusTextEl = document.getElementById("statusText");
const modelSelectEl = document.getElementById("modelSelect");
const contextWindowEl = document.getElementById("contextWindow");
const syncStatusEl = document.getElementById("syncStatus");

let config = DEFAULT_CONFIG;
let models = [];
let activeSessionId = null;
let selectedModelProfile = null;

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

function getModelByName(name) {
  return models.find((model) => model.name === name);
}

function getTokenWindow() {
  const model = getModelByName(selectedModelProfile);
  if (model && Number.isFinite(Number(model.context_window))) {
    return Number(model.context_window);
  }
  return config.token_window || DEFAULT_CONFIG.token_window;
}

function getRiskLevel(totalTokens) {
  const tokenWindow = getTokenWindow();
  const thresholds = config.risk_thresholds || DEFAULT_CONFIG.risk_thresholds;
  const score = tokenWindow > 0 ? totalTokens / tokenWindow : 1;
  if (score >= thresholds.red) {
    return "red";
  }
  if (score >= thresholds.yellow) {
    return "yellow";
  }
  return "green";
}

function updateUI(totalTokens) {
  sessionTokensEl.textContent = totalTokens;
  const tokenWindow = getTokenWindow();
  const percent = tokenWindow > 0
    ? Math.min(100, Math.round((totalTokens / tokenWindow) * 100))
    : 100;
  riskFillEl.style.width = `${percent}%`;

  const level = getRiskLevel(totalTokens);
  riskLabelEl.textContent = level;
  riskLabelEl.classList.remove("ai-risk--green", "ai-risk--yellow", "ai-risk--red");
  riskFillEl.classList.remove("ai-fill--green", "ai-fill--yellow", "ai-fill--red");

  riskLabelEl.classList.add(`ai-risk--${level}`);
  riskFillEl.classList.add(`ai-fill--${level}`);
}

function updateContextWindow() {
  const tokenWindow = getTokenWindow();
  contextWindowEl.textContent = tokenWindow > 0 ? tokenWindow.toLocaleString() : "-";
}

function renderLedgerStatus(status) {
  const normalized = status && ["synced", "waiting", "queued"].includes(status.state)
    ? status
    : { state: "synced", text: "Session synced" };
  syncStatusEl.textContent = normalized.text || "Session synced";
  syncStatusEl.classList.remove(
    "ai-sync-status--synced",
    "ai-sync-status--waiting",
    "ai-sync-status--queued"
  );
  syncStatusEl.classList.add(`ai-sync-status--${normalized.state}`);
}

async function loadLedgerStatus() {
  if (!activeSessionId) {
    renderLedgerStatus();
    return;
  }
  const stored = await storageGet([STORAGE_KEYS.ledgerStatus]);
  const statuses = stored[STORAGE_KEYS.ledgerStatus] || {};
  renderLedgerStatus(statuses[activeSessionId]);
}

function populateModelSelect() {
  modelSelectEl.innerHTML = "";
  if (!models.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Backend offline";
    modelSelectEl.appendChild(option);
    modelSelectEl.disabled = true;
    return;
  }

  modelSelectEl.disabled = false;
  for (const model of models) {
    const option = document.createElement("option");
    option.value = model.name;
    option.textContent = model.name;
    modelSelectEl.appendChild(option);
  }

  const model = getModelByName(selectedModelProfile) || models[0];
  selectedModelProfile = model ? model.name : config.default_model_profile;
  modelSelectEl.value = selectedModelProfile;
}

async function loadConfig() {
  const response = await AIUsageAPI.getConfig();
  if (response && response.success) {
    config = response.data;
  }
  return config;
}

async function loadModels() {
  const response = await AIUsageAPI.getModels();
  if (response && response.success) {
    models = response.data;
  }
  return models;
}

async function loadActiveSession() {
  const stored = await storageGet([STORAGE_KEYS.activeSession]);
  activeSessionId = stored[STORAGE_KEYS.activeSession] || null;
  return activeSessionId;
}

async function loadSelectedModel() {
  const stored = await storageGet([STORAGE_KEYS.modelProfile]);
  selectedModelProfile = stored[STORAGE_KEYS.modelProfile] || config.default_model_profile;
  if (!stored[STORAGE_KEYS.modelProfile]) {
    await storageSet({ [STORAGE_KEYS.modelProfile]: selectedModelProfile });
  }
  return selectedModelProfile;
}

async function syncSessionTokens() {
  if (!activeSessionId) {
    updateUI(0);
    return;
  }

  const response = await AIUsageAPI.getSession(activeSessionId);
  if (response && response.success) {
    const total = Number(response.data?.total_tokens) || 0;
    const stored = await storageGet([STORAGE_KEYS.sessionTokens]);
    const map = stored[STORAGE_KEYS.sessionTokens] || {};
    map[activeSessionId] = total;
    await storageSet({ [STORAGE_KEYS.sessionTokens]: map });
    updateUI(total);
    statusTextEl.textContent = "";
    return;
  }

  if (response && response.status === 404) {
    const stored = await storageGet([STORAGE_KEYS.sessionTokens]);
    const map = stored[STORAGE_KEYS.sessionTokens] || {};
    map[activeSessionId] = 0;
    await storageSet({ [STORAGE_KEYS.sessionTokens]: map });
    updateUI(0);
    statusTextEl.textContent = "Backend session restarted.";
    return;
  }

  const local = await storageGet([STORAGE_KEYS.sessionTokens]);
  const map = local[STORAGE_KEYS.sessionTokens] || {};
  const total = Number(map[activeSessionId]) || 0;
  updateUI(total);
  statusTextEl.textContent = "Backend not reachable.";
}

resetBtn.addEventListener("click", async () => {
  if (!activeSessionId) {
    updateUI(0);
    return;
  }

  const response = await AIUsageAPI.resetSession(activeSessionId, selectedModelProfile);
  if (response && response.success) {
    const total = Number(response.data?.session_tokens) || 0;
    const stored = await storageGet([STORAGE_KEYS.sessionTokens]);
    const map = stored[STORAGE_KEYS.sessionTokens] || {};
    map[activeSessionId] = total;
    await storageSet({ [STORAGE_KEYS.sessionTokens]: map });
    updateUI(total);
    statusTextEl.textContent = "Session reset.";
  } else {
    statusTextEl.textContent = "Backend not reachable.";
  }
});

modelSelectEl.addEventListener("change", async (event) => {
  const value = event.target.value;
  selectedModelProfile = value || config.default_model_profile;
  await storageSet({ [STORAGE_KEYS.modelProfile]: selectedModelProfile });
  updateContextWindow();
  syncSessionTokens();
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes[STORAGE_KEYS.sessionTokens] && activeSessionId) {
    const map = changes[STORAGE_KEYS.sessionTokens].newValue || {};
    updateUI(Number(map[activeSessionId]) || 0);
  }
  if (changes[STORAGE_KEYS.modelProfile]) {
    selectedModelProfile = changes[STORAGE_KEYS.modelProfile].newValue || config.default_model_profile;
    populateModelSelect();
    updateContextWindow();
  }
  if (changes[STORAGE_KEYS.activeSession]) {
    activeSessionId = changes[STORAGE_KEYS.activeSession].newValue || null;
    syncSessionTokens();
    loadLedgerStatus();
  }
  if (changes[STORAGE_KEYS.ledgerStatus] && activeSessionId) {
    const statuses = changes[STORAGE_KEYS.ledgerStatus].newValue || {};
    renderLedgerStatus(statuses[activeSessionId]);
  }
});

async function init() {
  await loadConfig();
  await loadModels();
  await loadActiveSession();
  await loadSelectedModel();
  populateModelSelect();
  updateContextWindow();
  await loadLedgerStatus();
  syncSessionTokens();
}

init();
