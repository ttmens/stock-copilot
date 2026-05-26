/** Runtime config — auto-detects API when served from FastAPI same origin */
(function() {
  if (!window.STOCK_COPILOT) window.STOCK_COPILOT = {};

  if (!window.STOCK_COPILOT.API_BASE) {
    // GitHub Pages static mode — no API
    if (window.location.hostname === "ttmens.github.io") {
      window.STOCK_COPILOT.API_BASE = "";
    }
    // Local dev — try same origin (FastAPI server serves static files too)
    else if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      window.STOCK_COPILOT.API_BASE = window.location.origin;
    }
    // IP access (server direct) — try same origin
    else {
      window.STOCK_COPILOT.API_BASE = window.location.origin;
    }
  }
})();
