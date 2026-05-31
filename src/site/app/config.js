/** Runtime config — static + Live Cockpit dual-track (Phase G) */
// Cache-bust: v3.0.0-alpha-20260531-fix-deep-mine
(function () {
  if (!window.STOCK_COPILOT) window.STOCK_COPILOT = {};

  const cfg = window.STOCK_COPILOT;

  // API base resolution priority:
  // 1. Cloudflare Tunnel (HTTPS, works from GitHub Pages)
  // 2. Same-origin (nginx 8081 direct access)
  if (!cfg.API_BASE) {
    if (
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1"
    ) {
      cfg.API_BASE = "";
    } else if (/^[\d.]+$/.test(window.location.hostname)) {
      // Direct IP access → same-origin (nginx 8081)
      cfg.API_BASE = "";
    } else if (window.location.hostname.endsWith("trycloudflare.com")) {
      // Already on cloudflare tunnel → same-origin
      cfg.API_BASE = "";
    } else {
      // GitHub Pages or other → use cloudflare tunnel
      cfg.API_BASE = "https://senator-salad-antibodies-any.trycloudflare.com";
    }
  }
})();
