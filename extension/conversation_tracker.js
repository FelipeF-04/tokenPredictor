(function attachConversationTracker(root, factory) {
  const tracker = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = tracker;
  }
  root.AIUsageConversationTracker = tracker;
})(typeof globalThis !== "undefined" ? globalThis : this, () => {
  function hashContent(value) {
    let hash = 2166136261;
    const text = String(value || "");
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  function create(options) {
    const storage = options.storage;
    const recordEvent = options.recordEvent;
    const stabilityMs = Number.isFinite(options.stabilityMs) ? options.stabilityMs : 2500;
    const setTimer = options.setTimeoutFn || setTimeout;
    const clearTimer = options.clearTimeoutFn || clearTimeout;
    let queue = [];
    let initialized = false;
    let initializing = null;
    let flushing = false;
    let currentSessionId = null;
    const candidateStates = new Map();
    const lastQueuedFingerprints = new Map();
    const waitingAssistants = new Set();

    function eventKey(payload) {
      return `${payload.session_id}\u0000${payload.event_id}`;
    }

    function fingerprint(payload) {
      return hashContent(`${payload.role}\u0000${payload.text}`);
    }

    function emitStatus() {
      let state = "synced";
      let text = "Session synced";
      if (queue.length > 0) {
        state = "queued";
        text = queue.length === 1 ? "1 event queued" : `${queue.length} events queued`;
      } else if (waitingAssistants.size > 0) {
        state = "waiting";
        text = "Waiting for response to finish";
      }
      if (typeof options.onStatus === "function") {
        options.onStatus({ state, text, pendingCount: queue.length });
      }
    }

    async function persistQueue() {
      try {
        await storage.save(queue.map((item) => ({ ...item })));
      } catch (error) {
        // Local storage failures must never block the chat page.
      }
    }

    async function initialize() {
      if (initialized) {
        return retryQueued();
      }
      if (initializing) {
        return initializing;
      }
      initializing = (async () => {
        try {
          const stored = await storage.load();
          queue = Array.isArray(stored) ? stored.filter((item) => item && item.event_id) : [];
          for (const item of queue) {
            lastQueuedFingerprints.set(eventKey(item), fingerprint(item));
          }
        } catch (error) {
          queue = [];
        }
        initialized = true;
        initializing = null;
        emitStatus();
        return flushQueue();
      })();
      return initializing;
    }

    async function enqueue(payload, flush = true) {
      if (!initialized) {
        await initialize();
      }
      const key = eventKey(payload);
      const existingIndex = queue.findIndex((item) => eventKey(item) === key);
      if (existingIndex >= 0) {
        queue[existingIndex] = { ...payload };
      } else {
        queue.push({ ...payload });
      }
      lastQueuedFingerprints.set(key, fingerprint(payload));
      await persistQueue();
      emitStatus();
      return flush ? flushQueue() : null;
    }

    async function flushQueue() {
      if (!initialized || flushing) {
        return;
      }
      flushing = true;
      try {
        while (queue.length > 0) {
          const pending = { ...queue[0] };
          let response;
          try {
            response = await recordEvent(pending);
          } catch (error) {
            response = { success: false, error: error?.message || "Backend unavailable" };
          }
          if (!response || !response.success) {
            break;
          }

          const key = eventKey(pending);
          const pendingFingerprint = fingerprint(pending);
          const index = queue.findIndex((item) => eventKey(item) === key);
          if (index >= 0 && fingerprint(queue[index]) === pendingFingerprint) {
            queue.splice(index, 1);
            await persistQueue();
          }
          if (typeof options.onRecorded === "function") {
            await options.onRecorded(response.data, pending);
          }
        }
      } finally {
        flushing = false;
        emitStatus();
      }
    }

    async function retryQueued() {
      if (!initialized) {
        return initialize();
      }
      return flushQueue();
    }

    function cancelCandidateTimer(state) {
      if (state?.timerId !== null && state?.timerId !== undefined) {
        clearTimer(state.timerId);
        state.timerId = null;
      }
    }

    async function finalizeAssistant(key, expectedFingerprint) {
      const state = candidateStates.get(key);
      if (!state || state.fingerprint !== expectedFingerprint || state.candidate.streaming) {
        return;
      }
      state.timerId = null;
      waitingAssistants.delete(key);
      emitStatus();
      await enqueue(state.payload);
    }

    function scheduleAssistant(key, candidate, payload, payloadFingerprint) {
      const previous = candidateStates.get(key);
      if (previous && previous.fingerprint === payloadFingerprint && previous.timerId !== null) {
        return;
      }
      cancelCandidateTimer(previous);
      waitingAssistants.add(key);
      const state = {
        candidate,
        payload,
        fingerprint: payloadFingerprint,
        timerId: null,
      };
      state.timerId = setTimer(
        () => finalizeAssistant(key, payloadFingerprint),
        stabilityMs
      );
      candidateStates.set(key, state);
      emitStatus();
    }

    async function observe(rawCandidates, context) {
      await initialize();
      if (currentSessionId && currentSessionId !== context.sessionId) {
        for (const [key, state] of candidateStates) {
          if (key.startsWith(`${currentSessionId}\u0000`)) {
            cancelCandidateTimer(state);
            candidateStates.delete(key);
            waitingAssistants.delete(key);
          }
        }
        waitingAssistants.delete("pending-send");
      }
      currentSessionId = context.sessionId;
      const candidates = new Map();
      for (const candidate of Array.isArray(rawCandidates) ? rawCandidates : []) {
        if (!candidate || !candidate.eventId || !candidate.content) {
          continue;
        }
        const key = `${context.sessionId}\u0000${candidate.eventId}`;
        const previous = candidates.get(key);
        if (!previous || candidate.content.length >= previous.content.length) {
          candidates.set(key, {
            ...candidate,
            streaming: Boolean(candidate.streaming || previous?.streaming),
          });
        } else if (candidate.streaming) {
          previous.streaming = true;
        }
      }

      for (const [key, candidate] of candidates) {
        const payload = {
          session_id: context.sessionId,
          event_id: candidate.eventId,
          role: candidate.role,
          text: candidate.content,
          model_profile: context.modelProfile,
        };
        const payloadFingerprint = fingerprint(payload);
        if (candidate.role === "assistant") {
          waitingAssistants.delete("pending-send");
        }
        if (lastQueuedFingerprints.get(key) === payloadFingerprint) {
          waitingAssistants.delete(key);
          cancelCandidateTimer(candidateStates.get(key));
          continue;
        }

        if (candidate.role === "user") {
          waitingAssistants.delete(key);
          cancelCandidateTimer(candidateStates.get(key));
          candidateStates.set(key, {
            candidate,
            payload,
            fingerprint: payloadFingerprint,
            timerId: null,
          });
          await enqueue(payload, false);
          continue;
        }

        if (candidate.role === "assistant" && candidate.streaming) {
          const previous = candidateStates.get(key);
          cancelCandidateTimer(previous);
          candidateStates.set(key, {
            candidate,
            payload,
            fingerprint: payloadFingerprint,
            timerId: null,
          });
          waitingAssistants.add(key);
          emitStatus();
          continue;
        }

        if (candidate.role === "assistant") {
          scheduleAssistant(key, candidate, payload, payloadFingerprint);
        }
      }
      await flushQueue();
      emitStatus();
    }

    function markWaiting() {
      waitingAssistants.add("pending-send");
      emitStatus();
    }

    function getState() {
      return {
        queue: queue.map((item) => ({ ...item })),
        waitingCount: waitingAssistants.size,
        initialized,
      };
    }

    function dispose() {
      for (const state of candidateStates.values()) {
        cancelCandidateTimer(state);
      }
      candidateStates.clear();
      waitingAssistants.clear();
    }

    return {
      initialize,
      observe,
      retryQueued,
      markWaiting,
      getState,
      dispose,
    };
  }

  return { create, hashContent };
});
