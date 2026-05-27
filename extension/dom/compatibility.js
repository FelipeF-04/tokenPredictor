const AIUsageDomCompatibility = (() => {
  function detectHost(locationObj) {
    const hostname = locationObj?.hostname || "";
    if (hostname.includes("chatgpt.com")) {
      return "chatgpt.com";
    }
    if (hostname.includes("chat.openai.com")) {
      return "chat.openai.com";
    }
    return "unknown";
  }

  function isSupportedHost(locationObj) {
    const host = detectHost(locationObj);
    return host === "chatgpt.com" || host === "chat.openai.com";
  }

  function describe(documentObj) {
    const host = detectHost(documentObj?.location || window.location);
    const hasMessageRole = Boolean(
      documentObj?.querySelector?.("[data-message-author-role]")
    );
    return {
      host,
      supported: isSupportedHost(documentObj?.location || window.location),
      hasMessageRole,
    };
  }

  return {
    detectHost,
    isSupportedHost,
    describe,
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = AIUsageDomCompatibility;
}
