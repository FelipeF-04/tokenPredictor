const assert = require("node:assert/strict");
const test = require("node:test");

const { create } = require("../content_controller.js");

function createScheduler() {
  let scheduled = null;
  return {
    setTimeoutFn(callback) {
      scheduled = callback;
      return 1;
    },
    clearTimeoutFn() {
      scheduled = null;
    },
    async flush() {
      assert.ok(scheduled, "expected a debounced callback");
      const callback = scheduled;
      scheduled = null;
      await callback();
    },
  };
}

test("typing invokes analyze rather than optimize", async () => {
  const calls = { analyze: [], optimize: [] };
  const scheduler = createScheduler();
  const controller = create({
    api: {
      async analyze(...args) {
        calls.analyze.push(args);
        return { success: true, data: { input_tokens: 4 } };
      },
      async optimize(payload) {
        calls.optimize.push(payload);
        return { success: true, data: {} };
      },
    },
    ...scheduler,
  });

  controller.scheduleAnalyze("draft prompt", {
    sessionId: "session-1",
    modelProfile: "local-8k",
  });
  assert.equal(calls.analyze.length, 0, "analysis should be debounced");
  await scheduler.flush();

  assert.deepEqual(calls.analyze, [["draft prompt", "session-1", "local-8k"]]);
  assert.equal(calls.optimize.length, 0);
});

test("optimization runs only after an explicit request", async () => {
  let analyzeCalls = 0;
  let optimizeCalls = 0;
  const scheduler = createScheduler();
  const controller = create({
    api: {
      async analyze() {
        analyzeCalls += 1;
        return { success: true, data: { input_tokens: 2 } };
      },
      async optimize() {
        optimizeCalls += 1;
        return { success: true, data: { optimized: {} } };
      },
    },
    ...scheduler,
  });

  controller.scheduleAnalyze("draft", { sessionId: "s", modelProfile: "m" });
  await scheduler.flush();
  assert.equal(analyzeCalls, 1);
  assert.equal(optimizeCalls, 0);

  await controller.optimize({ messages: [{ role: "user", content: "draft" }] });
  assert.equal(optimizeCalls, 1);
});

test("optimization failure preserves the live estimate", async () => {
  const scheduler = createScheduler();
  const view = { estimateVisible: false, error: "" };
  const controller = create({
    api: {
      async analyze() {
        return {
          success: true,
          data: { input_tokens: 8, predicted_output_tokens: 10, risk_level: "green" },
        };
      },
      async optimize() {
        return { success: false, error: "Embedding model is unavailable" };
      },
    },
    onLiveSuccess() {
      view.estimateVisible = true;
    },
    onOptimizeError(error) {
      view.error = error;
    },
    ...scheduler,
  });

  controller.scheduleAnalyze("keep this estimate", {
    sessionId: "session-2",
    modelProfile: "gpt-4o-mini",
  });
  await scheduler.flush();
  await controller.optimize({ messages: [{ role: "user", content: "keep this estimate" }] });

  assert.equal(view.estimateVisible, true);
  assert.equal(view.error, "Embedding model is unavailable");
  assert.equal(controller.getState().liveEstimate.input_tokens, 8);
  assert.equal(controller.getState().optimizationError, "Embedding model is unavailable");
});
