const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const compatibility = require(path.join(__dirname, "..", "dom", "compatibility.js"));

function mockDocument(hostname) {
  return {
    location: { hostname },
    querySelector: () => null,
  };
}

test("supported ChatGPT hosts are detected", () => {
  for (const hostname of ["chatgpt.com", "chat.openai.com"]) {
    const document = mockDocument(hostname);
    assert.equal(compatibility.detectHost(document.location), hostname);
    assert.equal(compatibility.isSupportedHost(document.location), true);
  }
});

test("unrelated hosts are rejected", () => {
  const document = mockDocument("example.com");
  assert.equal(compatibility.detectHost(document.location), "unknown");
  assert.equal(compatibility.isSupportedHost(document.location), false);
});
