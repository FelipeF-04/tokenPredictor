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

  function uniqueMessageNodes(root) {
    const nodes = findAllMatches(AIUsageDomSelectors.message, root);
    return Array.from(new Set(nodes));
  }

  function ancestors(node) {
    const results = [];
    let current = node;
    while (current) {
      results.push(current);
      current = current.parentElement;
    }
    return results;
  }

  function normalizeIdentifier(value) {
    return String(value || "").trim().replace(/\s+/g, "-").slice(0, 220);
  }

  function getStableEventId(node, role, fallbackIndex) {
    const hierarchy = ancestors(node);
    for (const candidate of hierarchy) {
      const testId = candidate.getAttribute?.("data-testid") || "";
      if (testId.startsWith("conversation-turn-")) {
        return `turn:${normalizeIdentifier(testId)}:${role}`;
      }
    }
    for (const candidate of hierarchy) {
      const messageId = candidate.getAttribute?.("data-message-id");
      if (messageId) {
        return `message:${normalizeIdentifier(messageId)}:${role}`;
      }
    }
    for (const candidate of hierarchy) {
      const elementId = candidate.getAttribute?.("id");
      if (elementId && elementId !== "prompt-textarea") {
        return `element:${normalizeIdentifier(elementId)}:${role}`;
      }
    }
    return `fallback:${role}:${fallbackIndex}`;
  }

  function hasStreamingMarker(node) {
    for (const candidate of ancestors(node)) {
      const streaming = candidate.getAttribute?.("data-is-streaming");
      const busy = candidate.getAttribute?.("aria-busy");
      const className = candidate.getAttribute?.("class") || "";
      if (
        streaming === "true" ||
        busy === "true" ||
        className.split(/\s+/).includes("result-streaming")
      ) {
        return true;
      }
    }
    return false;
  }

  function extractMessageEvents(root) {
    const nodes = uniqueMessageNodes(root);
    const results = [];
    const roleIndexes = { user: 0, assistant: 0 };
    for (const node of nodes) {
      const role = (node.getAttribute(AIUsageDomSelectors.roleAttribute) || "").trim();
      if (role !== "user" && role !== "assistant") {
        continue;
      }
      const content = (node.innerText || "").trim();
      if (!content) {
        continue;
      }
      roleIndexes[role] += 1;
      results.push({
        eventId: getStableEventId(node, role, roleIndexes[role]),
        role,
        content,
        streaming: role === "assistant" && hasStreamingMarker(node),
        node,
      });
    }

    const stopButton = findFirstMatch(AIUsageDomSelectors.stopButton, root);
    if (stopButton) {
      for (let index = results.length - 1; index >= 0; index -= 1) {
        if (results[index].role === "assistant") {
          results[index].streaming = true;
          break;
        }
      }
    }

    const deduplicated = new Map();
    for (const result of results) {
      const existing = deduplicated.get(result.eventId);
      if (!existing || result.content.length >= existing.content.length) {
        deduplicated.set(result.eventId, {
          ...result,
          streaming: Boolean(result.streaming || existing?.streaming),
        });
      } else if (result.streaming) {
        existing.streaming = true;
      }
    }
    return Array.from(deduplicated.values());
  }

  function extractMessages(root, maxMessages) {
    const events = extractMessageEvents(root);
    const results = [];
    const seen = new Set();
    for (const { role, content } of events) {
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
    extractMessageEvents,
  };
})();
