/** Unified API client — Phase G */
(function () {
  "use strict";

  const cfg = window.STOCK_COPILOT || {};
  const API = (cfg.API_BASE || "").replace(/\/$/, "");

  async function apiFetch(path, options) {
    if (!API) {
      const err = new Error("API unavailable");
      err.offline = true;
      throw err;
    }
    const res = await fetch(`${API}${path}`, options || {});
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
    base: API,
    fetch: apiFetch,
    showLiveBanner,
    showStale,
    isOnline: () => !!API,
  };

  if (!API) showLiveBanner(true);
})();
