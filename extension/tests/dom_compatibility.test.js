const assert = require("assert");
const path = require("path");

const compatibility = require(path.join(__dirname, "..", "dom", "compatibility.js"));

function mockDocument(hostname) {
  return {
    location: { hostname },
    querySelector: () => null,
  };
}

const chatgpt = mockDocument("chatgpt.com");
const openai = mockDocument("chat.openai.com");
const other = mockDocument("example.com");

assert.strictEqual(compatibility.detectHost(chatgpt.location), "chatgpt.com");
assert.strictEqual(compatibility.detectHost(openai.location), "chat.openai.com");
assert.strictEqual(compatibility.detectHost(other.location), "unknown");

assert.strictEqual(compatibility.isSupportedHost(chatgpt.location), true);
assert.strictEqual(compatibility.isSupportedHost(openai.location), true);
assert.strictEqual(compatibility.isSupportedHost(other.location), false);

console.log("dom_compatibility.test.js passed");
