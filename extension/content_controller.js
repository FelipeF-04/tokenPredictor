(function attachContentController(root, factory) {
  const controller = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = controller;
  }
  root.AIUsageContentController = controller;
})(typeof globalThis !== "undefined" ? globalThis : this, () => {
  function create(options) {
    const api = options.api;
    const debounceMs = Number.isFinite(options.debounceMs) ? options.debounceMs : 300;
    const setTimer = options.setTimeoutFn || setTimeout;
    const clearTimer = options.clearTimeoutFn || clearTimeout;
    let debounceId = null;
    let liveRequestId = 0;
    let liveEstimate = null;
    let optimization = null;
    let optimizationError = "";
    let optimizing = false;

    function emit(name, ...args) {
      if (typeof options[name] === "function") {
        options[name](...args);
      }
    }

    function invalidateLive() {
      liveRequestId += 1;
      if (debounceId !== null) {
        clearTimer(debounceId);
        debounceId = null;
      }
    }

    async function analyzeNow(message, context, requestId) {
      let response;
      try {
        response = await api.analyze(message, context.sessionId, context.modelProfile);
      } catch (error) {
        response = { success: false, error: error?.message || "Live estimate failed" };
      }

      if (requestId !== liveRequestId) {
        return response;
      }

      if (response && response.success) {
        liveEstimate = { ...response.data, message };
        emit("onLiveSuccess", response.data, message);
      } else {
        emit("onLiveError", response?.error || "Live estimate unavailable");
      }
      return response;
    }

    function scheduleAnalyze(rawMessage, context) {
      const message = typeof rawMessage === "string" ? rawMessage.trim() : "";
      invalidateLive();
      if (!message) {
        liveEstimate = null;
        emit("onLiveClear");
        return;
      }

      const requestId = liveRequestId;
      debounceId = setTimer(() => {
        debounceId = null;
        return analyzeNow(message, context, requestId);
      }, debounceMs);
    }

    async function optimize(payload) {
      if (optimizing) {
        return { success: false, error: "Optimization already in progress" };
      }

      optimizing = true;
      optimization = null;
      optimizationError = "";
      emit("onOptimizeStart");
      let response;
      try {
        response = await api.optimize(payload);
      } catch (error) {
        response = { success: false, error: error?.message || "Optimization failed" };
      }

      optimizing = false;
      if (response && response.success) {
        optimization = response.data;
        emit("onOptimizeSuccess", response.data);
      } else {
        optimizationError = response?.error || "Optimization failed";
        emit("onOptimizeError", optimizationError);
      }
      return response;
    }

    function getState() {
      return {
        liveEstimate,
        optimization,
        optimizationError,
        optimizing,
      };
    }

    function dispose() {
      invalidateLive();
    }

    return {
      scheduleAnalyze,
      optimize,
      getState,
      invalidateLive,
      dispose,
    };
  }

  return { create };
});
