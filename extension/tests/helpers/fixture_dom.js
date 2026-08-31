const fs = require("node:fs");
const path = require("node:path");

const VOID_ELEMENTS = new Set(["br", "hr", "img", "input", "link", "meta"]);

function decodeEntities(text) {
  return text
    .replaceAll("&amp;", "&")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'");
}

function descendants(element) {
  const results = [];
  for (const child of element.children) {
    results.push(child, ...descendants(child));
  }
  return results;
}

function matchesSimpleSelector(element, selector) {
  const tagMatch = selector.match(/^([a-z][\w-]*)/i);
  if (tagMatch && element.tagName !== tagMatch[1].toUpperCase()) {
    return false;
  }

  const attributePattern = /\[([^\]\s=*]+)(?:([*]?=)["']?([^"'\]]*)["']?)?\]/g;
  let attributeMatch = attributePattern.exec(selector);
  while (attributeMatch) {
    const [, name, operator, expected] = attributeMatch;
    const actual = element.getAttribute(name);
    if (actual === null) {
      return false;
    }
    if (operator === "=" && actual !== expected) {
      return false;
    }
    if (operator === "*=" && !actual.includes(expected)) {
      return false;
    }
    attributeMatch = attributePattern.exec(selector);
  }
  return true;
}

function matchesSelector(element, parts, index = parts.length - 1) {
  if (!matchesSimpleSelector(element, parts[index])) {
    return false;
  }
  if (index === 0) {
    return true;
  }

  let ancestor = element.parentElement;
  while (ancestor) {
    if (matchesSelector(ancestor, parts, index - 1)) {
      return true;
    }
    ancestor = ancestor.parentElement;
  }
  return false;
}

class FixtureElement {
  constructor(tagName, attributes = {}) {
    this.tagName = tagName.toUpperCase();
    this.attributes = { ...attributes };
    this.children = [];
    this.parentElement = null;
    this.value = attributes.value || "";
    this.focused = false;
    this.dispatchedEvents = [];
    this._text = "";
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
  }

  appendText(text) {
    this._text += decodeEntities(text);
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name)
      ? this.attributes[name]
      : null;
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  get innerText() {
    return this.textContent;
  }

  querySelectorAll(selector) {
    const parts = selector.trim().split(/\s+/);
    return descendants(this).filter((element) => matchesSelector(element, parts));
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  getBoundingClientRect() {
    const hidden = this.getAttribute("hidden") !== null;
    const style = this.getAttribute("style") || "";
    if (hidden || /display\s*:\s*none/i.test(style)) {
      return { width: 0, height: 0, top: 0, right: 0, bottom: 0, left: 0 };
    }
    return { width: 320, height: 40, top: 0, right: 320, bottom: 40, left: 0 };
  }

  focus() {
    this.focused = true;
  }

  dispatchEvent(event) {
    this.dispatchedEvents.push(event);
    return true;
  }
}

class FixtureDocument extends FixtureElement {
  constructor() {
    super("#document");
  }
}

class FixtureEvent {
  constructor(type, options = {}) {
    this.type = type;
    this.bubbles = Boolean(options.bubbles);
  }
}

function parseAttributes(source) {
  const attributes = {};
  const pattern = /([^\s=/>]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
  let match = pattern.exec(source);
  while (match) {
    attributes[match[1]] = match[2] ?? match[3] ?? match[4] ?? "";
    match = pattern.exec(source);
  }
  return attributes;
}

function parseHTML(html) {
  const document = new FixtureDocument();
  const stack = [document];
  const tokens = html.match(/<!--[\s\S]*?-->|<![^>]*>|<[^>]+>|[^<]+/g) || [];

  for (const token of tokens) {
    if (token.startsWith("<!--") || token.startsWith("<!")) {
      continue;
    }
    if (token.startsWith("</")) {
      const closingTag = token.slice(2, -1).trim().toUpperCase();
      while (stack.length > 1 && stack.at(-1).tagName !== closingTag) {
        stack.pop();
      }
      if (stack.length > 1) {
        stack.pop();
      }
      continue;
    }
    if (token.startsWith("<")) {
      const start = token.match(/^<([a-z][\w-]*)([\s\S]*?)\/?>(?:\s*)$/i);
      if (!start) {
        continue;
      }
      const tagName = start[1];
      const element = new FixtureElement(tagName, parseAttributes(start[2]));
      stack.at(-1).appendChild(element);
      const selfClosing = token.endsWith("/>") || VOID_ELEMENTS.has(tagName.toLowerCase());
      if (!selfClosing) {
        stack.push(element);
      }
      continue;
    }
    stack.at(-1).appendText(token);
  }
  return document;
}

function loadFixture(name) {
  const fixturePath = path.join(__dirname, "..", "fixtures", name);
  return parseHTML(fs.readFileSync(fixturePath, "utf8"));
}

module.exports = {
  FixtureEvent,
  loadFixture,
  parseHTML,
};
