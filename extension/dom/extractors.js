const AIUsageDomExtractors = (() => {
  function isVisible(element) {
    if (!element) {
      return false;
    }
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }

  function findFirstMatch(selectors, root) {
    for (const selector of selectors) {
      const match = root.querySelector(selector);
      if (match) {
        return match;
      }
    }
    return null;
  }

  function findAllMatches(selectors, root) {
    const results = [];
    for (const selector of selectors) {
      const matches = Array.from(root.querySelectorAll(selector));
      for (const match of matches) {
        results.push(match);
      }
    }
    return results;
  }

  function findInputElement(root) {
    const selectors = AIUsageDomSelectors.input;
    const candidates = findAllMatches(selectors, root).filter(isVisible);
    if (candidates.length > 0) {
      return candidates[candidates.length - 1];
    }
    return null;
  }

  function findSendButton(root) {
    return findFirstMatch(AIUsageDomSelectors.sendButton, root);
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

  function setInputValue(element, value) {
    if (!element) {
      return;
    }
    element.focus();
    if (element.tagName === "TEXTAREA" || element.tagName === "INPUT") {
      element.value = value;
      element.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    element.textContent = value;
    element.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function extractMessages(root, maxMessages) {
    const nodes = findAllMatches(AIUsageDomSelectors.message, root);
    const results = [];
    const seen = new Set();
    for (const node of nodes) {
      const role = (node.getAttribute(AIUsageDomSelectors.roleAttribute) || "").trim();
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

  return {
    isVisible,
    findInputElement,
    findSendButton,
    getInputValue,
    setInputValue,
    extractMessages,
  };
})();
