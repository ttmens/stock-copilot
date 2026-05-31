/** Runtime config — static + Live Cockpit dual-track (Phase G) */
(function () {
  if (!window.STOCK_COPILOT) window.STOCK_COPILOT = {};

  const cfg = window.STOCK_COPILOT;

  if (!cfg.PRODUCTION_API_BASE) {
    cfg.PRODUCTION_API_BASE = "";
  }

  if (!cfg.API_BASE) {
    if (window.location.hostname === "ttmens.github.io") {
      cfg.API_BASE = cfg.PRODUCTION_API_BASE || "";
    } else if (
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1"
    ) {
      cfg.API_BASE = window.location.origin;
    } else {
      cfg.API_BASE = window.location.origin;
    }
  }
})();
