const AIUsageDomSelectors = {
  input: [
    "textarea[data-id='root']",
    "textarea[placeholder*='Message']",
    "textarea",
    "div[contenteditable='true']",
    "[contenteditable='true'][data-placeholder]",
  ],
  sendButton: [
    "button[data-testid='send-button']",
    "button[aria-label*='Send']",
    "button[aria-label*='send']",
  ],
  message: [
    "[data-message-author-role]",
    "article [data-message-author-role]",
    "div[data-message-author-role]",
  ],
  roleAttribute: "data-message-author-role",
};
