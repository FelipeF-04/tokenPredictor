const DEFAULT_CONFIG = {
  version: "1.1.0",
  backend_base_url: "http://localhost:5000",
  default_model_profile: "gpt-4o-mini",
  token_window: 8000,
  output_estimate_min_tokens: 30,
  risk_thresholds: { yellow: 0.6, red: 0.85 },
  debug: { dom: false, pipeline: false },
  backend: { session_ttl_seconds: 7200 },
};

const CONFIG_CACHE_KEY = "aiUsageConfigCache";
const MODELS_CACHE_KEY = "aiUsageModelsCache";

let configCache = null;
let modelsCache = null;

function normalizeConfig(raw) {
  const source = typeof raw === "object" && raw ? raw : {};
  const risk = typeof source.risk_thresholds === "object" && source.risk_thresholds
    ? source.risk_thresholds
    : {};
  const debug = typeof source.debug === "object" && source.debug ? source.debug : {};
  const backend = typeof source.backend === "object" && source.backend ? source.backend : {};

  const yellow = Number(risk.yellow);
  const red = Number(risk.red);
  const normalized = {
    version: typeof source.version === "string" ? source.version : DEFAULT_CONFIG.version,
    backend_base_url:
      typeof source.backend_base_url === "string" && source.backend_base_url
        ? source.backend_base_url
        : DEFAULT_CONFIG.backend_base_url,
    default_model_profile:
      typeof source.default_model_profile === "string" && source.default_model_profile
        ? source.default_model_profile
        : DEFAULT_CONFIG.default_model_profile,
    token_window: Number.isFinite(Number(source.token_window))
      ? Math.max(Number(source.token_window), 0)
      : DEFAULT_CONFIG.token_window,
    output_estimate_min_tokens: Number.isFinite(Number(source.output_estimate_min_tokens))
      ? Math.max(Number(source.output_estimate_min_tokens), 0)
      : DEFAULT_CONFIG.output_estimate_min_tokens,
    risk_thresholds: {
      yellow: Number.isFinite(yellow) ? Math.min(Math.max(yellow, 0), 1) : DEFAULT_CONFIG.risk_thresholds.yellow,
      red: Number.isFinite(red) ? Math.min(Math.max(red, 0), 1) : DEFAULT_CONFIG.risk_thresholds.red,
    },
    debug: {
      dom: Boolean(debug.dom),
      pipeline: Boolean(debug.pipeline),
    },
    backend: {
      session_ttl_seconds: Number.isFinite(Number(backend.session_ttl_seconds))
        ? Math.max(Number(backend.session_ttl_seconds), 0)
        : DEFAULT_CONFIG.backend.session_ttl_seconds,
    },
  };

  if (normalized.risk_thresholds.red < normalized.risk_thresholds.yellow) {
    normalized.risk_thresholds.red = normalized.risk_thresholds.yellow;
  }
  return normalized;
}

async function loadLocalConfig() {
  try {
    const response = await fetch(chrome.runtime.getURL("shared/config.json"));
    if (!response.ok) {
      throw new Error("Failed to load local config");
    }
    const json = await response.json();
    return normalizeConfig(json);
  } catch (error) {
    return normalizeConfig(DEFAULT_CONFIG);
  }
}

async function getConfig() {
  if (configCache) {
    return configCache;
  }

  const localConfig = await loadLocalConfig();
  try {
    const response = await fetch(`${localConfig.backend_base_url}/config`);
    if (!response.ok) {
      throw new Error("Backend config failed");
    }
    const json = await response.json();
    const normalized = normalizeConfig({ ...localConfig, ...json });
    configCache = normalized;
    chrome.storage.local.set({ [CONFIG_CACHE_KEY]: normalized });
    return normalized;
  } catch (error) {
    const cached = await chrome.storage.local.get([CONFIG_CACHE_KEY]);
    configCache = normalizeConfig(cached[CONFIG_CACHE_KEY] || localConfig);
    return configCache;
  }
}

async function getModels() {
  if (modelsCache) {
    return modelsCache;
  }
  const config = await getConfig();
  try {
    const response = await fetch(`${config.backend_base_url}/models`);
    if (!response.ok) {
      throw new Error("Backend models failed");
    }
    const json = await response.json();
    const models = Array.isArray(json.models) ? json.models : [];
    modelsCache = models;
    chrome.storage.local.set({ [MODELS_CACHE_KEY]: models });
    return models;
  } catch (error) {
    const cached = await chrome.storage.local.get([MODELS_CACHE_KEY]);
    modelsCache = Array.isArray(cached[MODELS_CACHE_KEY]) ? cached[MODELS_CACHE_KEY] : [];
    return modelsCache;
  }
}

async function postJSON(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    data = null;
  }
  if (!response.ok) {
    const backendMessage = data && typeof data.error === "string" ? data.error : null;
    throw new Error(backendMessage || `Backend request failed (${response.status})`);
  }
  return data;
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getConfig") {
    getConfig()
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (request.action === "getModels") {
    getModels()
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (request.action === "getSession") {
    getConfig()
      .then((config) =>
        fetch(`${config.backend_base_url}/session/${request.session_id}`)
      )
      .then((response) => {
        if (!response.ok) {
          const error = new Error("Backend error");
          error.status = response.status;
          throw error;
        }
        return response.json();
      })
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) =>
        sendResponse({ success: false, error: error.message, status: error.status })
      );
    return true;
  }

  if (request.action === "resetSession") {
    getConfig()
      .then((config) =>
        postJSON(`${config.backend_base_url}/session/${request.session_id}/reset`, {
          model_profile: request.model_profile,
        })
      )
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (request.action === "analyze") {
    getConfig()
      .then((config) =>
        postJSON(`${config.backend_base_url}/analyze`, {
          message: request.message,
          session_id: request.session_id,
          model_profile: request.model_profile,
        })
      )
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true; // Keep channel open for async response
  }

  if (request.action === "optimize") {
    getConfig()
      .then((config) => postJSON(`${config.backend_base_url}/optimize`, request.payload || {}))
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (request.action === "recordEvent") {
    getConfig()
      .then((config) => postJSON(`${config.backend_base_url}/events`, request.payload || {}))
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }

  if (request.action === "commit") {
    getConfig()
      .then((config) =>
        postJSON(`${config.backend_base_url}/commit`, {
          delta_tokens: request.delta_tokens,
          session_id: request.session_id,
          model_profile: request.model_profile,
        })
      )
      .then((data) => sendResponse({ success: true, data }))
      .catch((error) => sendResponse({ success: false, error: error.message }));
    return true;
  }
});
