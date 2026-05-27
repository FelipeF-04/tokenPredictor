const AIUsageDomObservers = (() => {
  function createObserver(onChange, options = {}) {
    const baseDelay = Number.isFinite(options.baseDelay) ? options.baseDelay : 150;
    const maxDelay = Number.isFinite(options.maxDelay) ? options.maxDelay : 2000;
    const growth = Number.isFinite(options.growth) ? options.growth : 1.6;
    let delay = baseDelay;
    let timeoutId = null;

    function schedule() {
      if (timeoutId) {
        return;
      }
      timeoutId = setTimeout(() => {
        timeoutId = null;
        onChange();
      }, delay);
    }

    function notifyFailure() {
      delay = Math.min(maxDelay, delay * growth);
    }

    function notifySuccess() {
      delay = baseDelay;
    }

    const observer = new MutationObserver(() => {
      schedule();
    });

    function observe(target) {
      if (!target) {
        return;
      }
      observer.observe(target, { childList: true, subtree: true });
      schedule();
    }

    function disconnect() {
      observer.disconnect();
      if (timeoutId) {
        clearTimeout(timeoutId);
        timeoutId = null;
      }
    }

    return {
      observe,
      disconnect,
      schedule,
      notifyFailure,
      notifySuccess,
    };
  }

  return { createObserver };
})();
