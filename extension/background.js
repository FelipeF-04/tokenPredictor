const BACKEND_URL = "http://localhost:5000";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "analyze") {
    fetch(`${BACKEND_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: request.message }),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Backend error");
        }
        return response.json();
      })
      .then((data) => {
        sendResponse({ success: true, data });
      })
      .catch((error) => {
        sendResponse({ success: false, error: error.message });
      });
    return true; // Keep channel open for async response
  }

  if (request.action === "optimize") {
    fetch(`${BACKEND_URL}/optimize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request.payload || {}),
    })
      .then((response) => {
        if (!response.ok) {
          throw new Error("Backend error");
        }
        return response.json();
      })
      .then((data) => {
        sendResponse({ success: true, data });
      })
      .catch((error) => {
        sendResponse({ success: false, error: error.message });
      });
    return true;
  }

  if (request.action === "commit") {
    fetch(`${BACKEND_URL}/commit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ delta_tokens: request.delta_tokens }),
    }).catch(() => {});
    sendResponse({ success: true });
    return true;
  }
});
