const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const trackerModule = require("../conversation_tracker.js");
const { FixtureEvent, loadFixture } = require("./helpers/fixture_dom.js");

function loadExtractors() {
  const context = vm.createContext({ Event: FixtureEvent });
  for (const relativePath of ["dom/selectors.js", "dom/extractors.js"]) {
    const source = fs.readFileSync(path.join(__dirname, "..", relativePath), "utf8");
    vm.runInContext(source, context, { filename: relativePath });
  }
  return vm.runInContext("AIUsageDomExtractors", context);
}

function createScheduler() {
  let nextId = 1;
  const callbacks = new Map();
  return {
    setTimeoutFn(callback) {
      const id = nextId;
      nextId += 1;
      callbacks.set(id, callback);
      return id;
    },
    clearTimeoutFn(id) {
      callbacks.delete(id);
    },
    get pendingCount() {
      return callbacks.size;
    },
    async runAll() {
      while (callbacks.size > 0) {
        const pending = Array.from(callbacks.values());
        callbacks.clear();
        for (const callback of pending) {
          await callback();
        }
      }
    },
  };
}

function createDurableStorage(initial = []) {
  const state = { queue: structuredClone(initial) };
  return {
    state,
    adapter: {
      async load() {
        return structuredClone(state.queue);
      },
      async save(queue) {
        state.queue = structuredClone(queue);
      },
    },
  };
}

function createFakeBackend() {
  const events = new Map();
  const totals = new Map();
  const calls = [];
  let available = true;

  return {
    calls,
    events,
    totals,
    setAvailable(value) {
      available = value;
    },
    async recordEvent(payload) {
      calls.push(structuredClone(payload));
      if (!available) {
        return { success: false, error: "Backend unavailable" };
      }
      const key = `${payload.session_id}\u0000${payload.event_id}`;
      const tokenCount = payload.text.trim().split(/\s+/).filter(Boolean).length;
      const previous = events.get(key);
      const previousTokens = previous?.tokenCount || 0;
      const status = !previous
        ? "created"
        : previous.text === payload.text
          ? "unchanged"
          : "updated";
      events.set(key, { ...structuredClone(payload), tokenCount });
      const total = (totals.get(payload.session_id) || 0) + tokenCount - previousTokens;
      totals.set(payload.session_id, total);
      return {
        success: true,
        data: {
          event_status: status,
          event_tokens: tokenCount,
          session_id: payload.session_id,
          corrected_session_total: total,
        },
      };
    },
  };
}

function candidatesFrom(extractors, fixtureName) {
  return extractors.extractMessageEvents(loadFixture(fixtureName)).map((event) => ({
    eventId: event.eventId,
    role: event.role,
    content: event.content,
    streaming: event.streaming,
  }));
}

function makeTracker({ storage, backend, scheduler, statuses = [], recorded = [] }) {
  return trackerModule.create({
    storage,
    recordEvent: (payload) => backend.recordEvent(payload),
    stabilityMs: 25,
    setTimeoutFn: scheduler.setTimeoutFn,
    clearTimeoutFn: scheduler.clearTimeoutFn,
    onStatus: (status) => statuses.push(status),
    onRecorded: (data) => recorded.push(data),
  });
}

const extractors = loadExtractors();

test("streaming assistant content is committed only after a stable final DOM state", async () => {
  const storage = createDurableStorage();
  const backend = createFakeBackend();
  const scheduler = createScheduler();
  const statuses = [];
  const tracker = makeTracker({ storage: storage.adapter, backend, scheduler, statuses });

  const streaming = candidatesFrom(extractors, "chatgpt_streaming.html");
  assert.equal(streaming.find((event) => event.role === "assistant").streaming, true);
  await tracker.observe(streaming, { sessionId: "session-a", modelProfile: "gpt-4o-mini" });
  assert.equal(backend.calls.filter((call) => call.role === "assistant").length, 0);
  assert.equal(scheduler.pendingCount, 0);
  assert.equal(statuses.at(-1).state, "waiting");

  const complete = candidatesFrom(extractors, "chatgpt_streamed.html");
  await tracker.observe(complete, { sessionId: "session-a", modelProfile: "gpt-4o-mini" });
  assert.equal(scheduler.pendingCount, 1);
  assert.equal(backend.calls.filter((call) => call.role === "assistant").length, 0);

  await scheduler.runAll();
  assert.equal(backend.calls.filter((call) => call.role === "assistant").length, 1);
  assert.equal(statuses.at(-1).state, "synced");
});

test("duplicate DOM nodes collapse to one stable ledger event", () => {
  const events = candidatesFrom(extractors, "chatgpt_duplicates.html");
  assert.equal(events.length, 1);
  assert.equal(events[0].eventId, "turn:conversation-turn-8:assistant");
  assert.equal(events[0].content, "A duplicated response.");
});

test("a regenerated response updates the same event and corrects the total", async () => {
  const storage = createDurableStorage();
  const backend = createFakeBackend();
  const scheduler = createScheduler();
  const recorded = [];
  const tracker = makeTracker({ storage: storage.adapter, backend, scheduler, recorded });

  await tracker.observe(candidatesFrom(extractors, "chatgpt_streamed.html"), {
    sessionId: "session-regen",
    modelProfile: "gpt-4o-mini",
  });
  await scheduler.runAll();
  const totalBefore = backend.totals.get("session-regen");

  await tracker.observe(candidatesFrom(extractors, "chatgpt_regenerated.html"), {
    sessionId: "session-regen",
    modelProfile: "gpt-4o-mini",
  });
  await scheduler.runAll();

  assert.equal(backend.events.size, 2, "user and assistant retain stable ledger identities");
  assert.ok(backend.totals.get("session-regen") < totalBefore);
  assert.equal(recorded.at(-1).event_status, "updated");
});

test("reload recovery flushes a durable queue when the backend returns", async () => {
  const storage = createDurableStorage();
  const backend = createFakeBackend();
  const firstScheduler = createScheduler();
  backend.setAvailable(false);
  const firstTracker = makeTracker({
    storage: storage.adapter,
    backend,
    scheduler: firstScheduler,
  });

  await firstTracker.observe(
    [{ eventId: "turn:conversation-turn-1:user", role: "user", content: "Queued user turn" }],
    { sessionId: "session-reload", modelProfile: "gpt-4o-mini" }
  );
  assert.equal(storage.state.queue.length, 1);
  firstTracker.dispose();

  backend.setAvailable(true);
  const secondTracker = makeTracker({
    storage: storage.adapter,
    backend,
    scheduler: createScheduler(),
  });
  await secondTracker.initialize();

  assert.equal(storage.state.queue.length, 0);
  assert.equal(backend.events.size, 1);
  assert.equal(backend.calls.length, 2, "one failed attempt and one recovered attempt");
});

test("queued events retry without blocking and duplicate observations stay idempotent", async () => {
  const storage = createDurableStorage();
  const backend = createFakeBackend();
  const scheduler = createScheduler();
  const tracker = makeTracker({ storage: storage.adapter, backend, scheduler });
  const candidate = {
    eventId: "turn:conversation-turn-4:user",
    role: "user",
    content: "Retry this message",
  };

  backend.setAvailable(false);
  await tracker.observe([candidate], { sessionId: "session-retry", modelProfile: "gpt-4o-mini" });
  assert.equal(tracker.getState().queue.length, 1);

  backend.setAvailable(true);
  await tracker.retryQueued();
  await tracker.observe([candidate], { sessionId: "session-retry", modelProfile: "gpt-4o-mini" });

  assert.equal(tracker.getState().queue.length, 0);
  assert.equal(backend.events.size, 1);
  assert.equal(backend.totals.get("session-retry"), 3);
});

test("SPA navigation scopes identical DOM events to separate sessions", async () => {
  const storage = createDurableStorage();
  const backend = createFakeBackend();
  const scheduler = createScheduler();
  const tracker = makeTracker({ storage: storage.adapter, backend, scheduler });
  const events = candidatesFrom(extractors, "chatgpt_streamed.html");

  await tracker.observe(events, { sessionId: "session-one", modelProfile: "gpt-4o-mini" });
  await scheduler.runAll();
  await tracker.observe(events, { sessionId: "session-two", modelProfile: "gpt-4o-mini" });
  await scheduler.runAll();

  assert.equal(backend.events.size, 4);
  assert.equal(backend.totals.get("session-one"), backend.totals.get("session-two"));
});
