/** Unified API client — Phase G */
(function () {
  "use strict";

  const cfg = window.STOCK_COPILOT || {};
  // Empty string = same-origin (relative URL). "null" = truly offline.
  const API = cfg.API_BASE === null ? null : (cfg.API_BASE || "").replace(/\/$/, "");

  async function apiFetch(path, options) {
    if (API === null) {
      const err = new Error("API unavailable");
      err.offline = true;
      throw err;
    }
    const url = API ? `${API}${path}` : path;
    const res = await fetch(url, options || {});
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  function showLiveBanner(show) {
    const el = document.getElementById("live-banner");
    if (el) el.hidden = !show;
  }

  function showStale(el, updatedAt, intervalSec) {
    if (!el || !updatedAt) return;
    const age = (Date.now() - new Date(updatedAt).getTime()) / 1000;
    if (age > intervalSec * 2) {
      el.classList.add("stale-chip");
      el.title = "数据可能延迟";
    }
  }

  window.StockCopilotAPI = {
    base: API || window.location.origin,
    fetch: apiFetch,
    showLiveBanner,
    showStale,
    isOnline: () => API !== null,
  };
})();
