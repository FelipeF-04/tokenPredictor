const STORAGE_KEY = "sessionTokens";
const TOKEN_WINDOW = 8000;
const YELLOW_THRESHOLD = 0.6;
const RED_THRESHOLD = 0.85;
const BACKEND_URL = "http://localhost:5000";

const sessionTokensEl = document.getElementById("sessionTokens");
const riskFillEl = document.getElementById("riskFill");
const riskLabelEl = document.getElementById("riskLabel");
const resetBtn = document.getElementById("resetBtn");
const statusTextEl = document.getElementById("statusText");

function getRiskLevel(totalTokens) {
  const score = TOKEN_WINDOW > 0 ? totalTokens / TOKEN_WINDOW : 1;
  if (score >= RED_THRESHOLD) {
    return "red";
  }
  if (score >= YELLOW_THRESHOLD) {
    return "yellow";
  }
  return "green";
}

function updateUI(totalTokens) {
  sessionTokensEl.textContent = totalTokens;
  const percent = Math.min(100, Math.round((totalTokens / TOKEN_WINDOW) * 100));
  riskFillEl.style.width = `${percent}%`;

  const level = getRiskLevel(totalTokens);
  riskLabelEl.textContent = level;
  riskLabelEl.classList.remove("ai-risk--green", "ai-risk--yellow", "ai-risk--red");
  riskFillEl.classList.remove("ai-fill--green", "ai-fill--yellow", "ai-fill--red");

  riskLabelEl.classList.add(`ai-risk--${level}`);
  riskFillEl.classList.add(`ai-fill--${level}`);
}

function loadSessionTokens() {
  chrome.storage.local.get([STORAGE_KEY], (result) => {
    const total = Number(result[STORAGE_KEY]) || 0;
    updateUI(total);
  });
}

resetBtn.addEventListener("click", () => {
  chrome.storage.local.set({ [STORAGE_KEY]: 0 }, () => {
    updateUI(0);
    statusTextEl.textContent = "Session reset.";
  });

  fetch(`${BACKEND_URL}/commit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reset: true }),
  }).catch(() => {
    statusTextEl.textContent = "Backend not reachable.";
  });
});

chrome.storage.onChanged.addListener((changes) => {
  if (changes[STORAGE_KEY]) {
    updateUI(Number(changes[STORAGE_KEY].newValue) || 0);
  }
});

loadSessionTokens();
