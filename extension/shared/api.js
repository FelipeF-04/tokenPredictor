const AIUsageAPI = (() => {
  function request(message) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(message, (response) => {
        resolve(response || { success: false, error: "No response" });
      });
    });
  }

  return {
    getConfig() {
      return request({ action: "getConfig" });
    },
    getModels() {
      return request({ action: "getModels" });
    },
    getSession(sessionId) {
      return request({ action: "getSession", session_id: sessionId });
    },
    resetSession(sessionId, modelProfile) {
      return request({
        action: "resetSession",
        session_id: sessionId,
        model_profile: modelProfile,
      });
    },
    analyze(message, sessionId, modelProfile) {
      return request({
        action: "analyze",
        message,
        session_id: sessionId,
        model_profile: modelProfile,
      });
    },
    optimize(payload) {
      return request({ action: "optimize", payload });
    },
    commit(sessionId, deltaTokens, modelProfile) {
      return request({
        action: "commit",
        session_id: sessionId,
        delta_tokens: deltaTokens,
        model_profile: modelProfile,
      });
    },
  };
})();
