/** Live polling + Session Rail — Phase G */
(function () {
  "use strict";

  const PHASE_LABELS = {
    pre_market: "盘前 · 读情报/推荐池",
    auction: "竞价 · 09:15–09:25",
    morning: "盘中 · 上午交易",
    lunch: "午休",
    afternoon: "盘中 · 下午交易",
    post_market: "盘后 · 看复盘",
    closed: "休市",
  };

  const timers = [];

  function updateSessionRail(data) {
    const phaseEl = document.getElementById("session-phase");
    const countEl = document.getElementById("session-countdown");
    const ctaEl = document.getElementById("session-cta");
    if (!phaseEl) return;

    const session = data?.session || "pre_market";
    phaseEl.textContent = PHASE_LABELS[session] || session;

    if (countEl && data?.minutes_to_milestone != null) {
      countEl.textContent = data.next_milestone
        ? `距 ${data.next_milestone} ${data.minutes_to_milestone} 分钟`
        : "";
    }

    if (ctaEl && ctaEl.tagName === "A" && !document.getElementById("cockpit-root")) {
      const base = window.location.pathname.includes("/app/") ? "cockpit.html" : "app/cockpit.html";
      ctaEl.href = base + "#today";
    }
  }

  async function refreshSession() {
    const api = window.StockCopilotAPI;
    if (!api?.isOnline()) {
      updateSessionRail({ session: "pre_market" });
      return;
    }
    try {
      const data = await api.fetch("/api/market/session");
      updateSessionRail(data);
    } catch (_) {
      updateSessionRail({ session: "pre_market" });
    }
  }

  async function refreshAlertBadge() {
    const badge = document.getElementById("nav-alert-badge");
    if (!badge || !window.StockCopilotAPI?.isOnline()) return;
    try {
      const data = await window.StockCopilotAPI.fetch("/api/alerts?unread_only=true");
      const n = data.unread_count || 0;
      badge.textContent = n;
      badge.hidden = n === 0;
    } catch (_) {}
  }

  function startPoll(fn, intervalMs, onlyWhen) {
    const tick = async () => {
      if (onlyWhen && !onlyWhen()) return;
      try {
        await fn();
      } catch (_) {}
    };
    tick();
    const id = setInterval(tick, intervalMs);
    timers.push(id);
    return id;
  }

  function symbolLink(code) {
    sessionStorage.setItem("last_symbol", code);
    const base = window.location.pathname.includes("/app/") ? "stock.html" : "app/stock.html";
    window.location.href = `${base}?code=${code}`;
  }

  window.StockCopilotLive = {
    refreshSession,
    refreshAlertBadge,
    startPoll,
    symbolLink,
    updateSessionRail,
    PHASE_LABELS,
  };

  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("cockpit-root")) return;
    refreshSession();
    refreshAlertBadge();
    startPoll(refreshSession, 60000);
    startPoll(refreshAlertBadge, 120000);
  });
})();
