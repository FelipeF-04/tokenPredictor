const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const { FixtureEvent, loadFixture } = require("./helpers/fixture_dom.js");

function loadExtractors() {
  const context = vm.createContext({ Event: FixtureEvent });
  for (const relativePath of ["dom/selectors.js", "dom/extractors.js"]) {
    const source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
    vm.runInContext(source, context, { filename: relativePath });
  }
  return vm.runInContext("AIUsageDomExtractors", context);
}

const extractors = loadExtractors();

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

for (const fixtureName of ["chatgpt_current.html", "chatgpt_legacy.html"]) {
  test(`${fixtureName} exposes the prompt input and send button`, () => {
    const document = loadFixture(fixtureName);

    const input = extractors.findInputElement(document);
    const sendButton = extractors.findSendButton(document);

    assert.ok(input, "prompt input should be discoverable");
    assert.ok(sendButton, "send button should be discoverable");
    assert.equal(sendButton.tagName, "BUTTON");
  });
}

test("current fixture extracts ordered, deduplicated conversation messages", () => {
  const document = loadFixture("chatgpt_current.html");

  assert.deepEqual(plain(extractors.extractMessages(document, 10)), [
    { role: "user", content: "Explain the compatibility guardrails." },
    { role: "assistant", content: "They keep API and DOM behavior stable." },
    { role: "user", content: "Keep the tests offline." },
  ]);
  assert.deepEqual(plain(extractors.extractMessages(document, 2)), [
    { role: "assistant", content: "They keep API and DOM behavior stable." },
    { role: "user", content: "Keep the tests offline." },
  ]);
});

test("legacy fixture extracts conversation messages", () => {
  const document = loadFixture("chatgpt_legacy.html");

  assert.deepEqual(plain(extractors.extractMessages(document, 10)), [
    { role: "user", content: "Legacy user message" },
    { role: "assistant", content: "Legacy assistant message" },
  ]);
});

test("contenteditable prompt updates focus, text, and dispatch input", () => {
  const document = loadFixture("chatgpt_current.html");
  const input = extractors.findInputElement(document);

  assert.equal(input.tagName, "DIV");
  assert.equal(input.getAttribute("contenteditable"), "true");
  extractors.setInputValue(input, "Updated optimized prompt");

  assert.equal(input.focused, true);
  assert.equal(input.textContent, "Updated optimized prompt");
  assert.equal(extractors.getInputValue(input), "Updated optimized prompt");
  assert.equal(input.dispatchedEvents.length, 1);
  assert.equal(input.dispatchedEvents[0].type, "input");
  assert.equal(input.dispatchedEvents[0].bubbles, true);
});
