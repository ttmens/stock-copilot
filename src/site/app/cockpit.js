/** Unified Cockpit — Journey Focus/Peek + ui-render */
(function () {
  "use strict";

  const UI = () => window.StockCopilotUI;
  const SESSION_PANEL = {
    pre_market: "panel-digest",
    auction: "panel-auction",
    morning: "panel-live",
    lunch: "panel-live",
    afternoon: "panel-live",
    post_market: "panel-review",
    closed: "panel-review",
  };
  const PHASE_HINTS = {
    pre_market: "先读情报与推荐池，确认今日战术方向",
    auction: "关注池内竞价量比与偏离度",
    morning: "盯预警流，池内标的按需跟进",
    lunch: "午休可回顾推荐池与上午预警",
    afternoon: "继续盯盘，留意午后异动",
    post_market: "查看命中与遗漏，总结明日策略",
    closed: "休市 — 可回顾复盘或自选研究",
  };

  let currentSession = "pre_market";
  let poolCache = { sectors: [] };
  let reviewCache = null;
  let alertCount = 0;
  let compareStocks = [];

  function api() { return window.StockCopilotAPI; }
  function live() { return window.StockCopilotLive; }
  function layout() { return window.StockCopilotLayout; }
  function stockHref(code) { return `stock.html?code=${code}`; }

  async function fetchJson(path, staticPath) {
    try {
      if (api()?.isOnline()) return await api().fetch(path);
    } catch (_) {}
    const r = await fetch(staticPath);
    return r.ok ? r.json() : null;
  }

  function updateHeaderMeta(meta) {
    const el = document.getElementById("header-meta");
    if (!el || !meta) return;
    const date = meta.trade_date || "";
    const time = (meta.generated_at || "").slice(11, 16);
    el.textContent = date && time ? `${date} · ${time}` : date || "";
  }

  function updateHero(session, data) {
    const phase = document.getElementById("hero-phase");
    const hint = document.getElementById("hero-hint");
    const countdown = document.getElementById("hero-countdown");
    const labels = live()?.PHASE_LABELS || {};
    if (phase) phase.textContent = labels[session] || session;
    if (hint) hint.textContent = PHASE_HINTS[session] || PHASE_HINTS.pre_market;
    if (countdown && data?.minutes_to_milestone != null && data.next_milestone) {
      countdown.textContent = `距 ${data.next_milestone} ${data.minutes_to_milestone} 分钟`;
    } else if (countdown) countdown.textContent = "";
  }

  function poolStockCount(data) {
    return (data?.sectors || []).reduce((n, s) => n + (s.stocks || []).length, 0);
  }

  function poolTopScore(data) {
    let top = -Infinity;
    (data?.sectors || []).forEach((s) => (s.stocks || []).forEach((st) => {
      const sc = Number(st.score) || 0;
      if (sc > top) top = sc;
    }));
    return top > -Infinity ? top.toFixed(2) : "—";
  }

  function updatePeekSummaries() {
    const set = (id, text) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (text) { el.textContent = text; el.hidden = false; }
      else el.hidden = true;
    };
    set("peek-pool", poolStockCount(poolCache) ? `推荐池 ${poolStockCount(poolCache)} 只 · 最高 ${poolTopScore(poolCache)}` : "");
    set("peek-live", alertCount ? `${alertCount} 条未读预警` : "");
    if (reviewCache) {
      const rate = ((reviewCache.hit_rate || 0) * 100).toFixed(1);
      set("peek-review", `命中率 ${rate}% · 命中 ${reviewCache.hit_count || 0}`);
    }
  }

  async function loadDigest() {
    const data = await fetchJson("/api/digest/today", "../data/digest.json");
    const meta = document.getElementById("digest-meta");
    const hot = document.getElementById("digest-hot");
    if (!data) {
      if (meta) meta.textContent = "暂无情报";
      return null;
    }
    if (meta) meta.textContent = `${data.trade_date || ""} · ${(data.generated_at || "").slice(0, 16)}`;
    if (hot && UI()) {
      hot.innerHTML = (data.hot_events || []).slice(0, 5).map((e) => UI().renderHotEvent(e)).join("");
    }
    const macro = document.getElementById("digest-macro");
    if (macro) macro.textContent = data.macro_summary || "—";
    const ov = document.getElementById("digest-overnight");
    if (ov && UI()) {
      const on = data.overnight || {};
      ov.innerHTML = Object.entries(on)
        .filter(([k]) => k !== "strong_foreign_impact")
        .map(([k, v]) => {
          const val = typeof v === "object" ? `${v.change_pct ?? ""}%` : v;
          return `<div class="metric-chip"><span class="metric-chip-label">${UI().esc(k)}</span><span class="metric-chip-val">${UI().esc(val)}</span></div>`;
        })
        .join("");
      (data.futures || []).forEach((f) => {
        ov.innerHTML += `<div class="metric-chip"><span class="metric-chip-label">${UI().esc(f.symbol)}</span><span class="metric-chip-val">${f.change_pct}%</span></div>`;
      });
    }
    const risks = document.getElementById("digest-risks");
    if (risks && UI()) {
      risks.innerHTML = (data.risk_flags || []).map((r) => `<li>${UI().esc(r)}</li>`).join("");
    }
    const peekDigest = document.getElementById("peek-digest");
    if (peekDigest) {
      peekDigest.textContent = (data.hot_events || []).length ? `${data.hot_events.length} 条热点` : "";
      peekDigest.hidden = !(data.hot_events || []).length;
    }
    return data;
  }

  function renderPool(data) {
    const root = document.getElementById("pool-root");
    if (!root || !UI()) return;
    poolCache = data || { sectors: [] };
    root.innerHTML = (poolCache.sectors || []).map((sec) => UI().renderPoolSector(sec, (c) => stockHref(c))).join("");
    updatePeekSummaries();
  }

  async function loadPool() {
    const data = await fetchJson("/api/recommendations/today", "../data/recommendation.json");
    renderPool(data || { sectors: [] });
    return data;
  }

  async function loadAuction() {
    const statusEl = document.getElementById("auction-status");
    const empty = document.getElementById("auction-empty");
    const tbody = document.querySelector("#auction-table tbody");
    const cards = document.getElementById("auction-cards");
    if (!api()?.isOnline()) {
      if (empty) empty.hidden = false;
      return;
    }
    try {
      const data = await api().fetch("/api/auction/latest");
      const snaps = data.snapshots || [];
      if (statusEl) statusEl.textContent = data.in_auction_window ? "竞价中" : "最近快照";
      if (empty) empty.hidden = data.in_auction_window || snaps.length > 0;
      if (tbody && UI()) tbody.innerHTML = snaps.map((s) => UI().renderAuctionRow(s, { href: stockHref(s.code) })).join("");
      if (cards && UI()) cards.innerHTML = snaps.map((s) => UI().renderAuctionRow(s, { mobile: true, href: stockHref(s.code) })).join("");
      const peek = document.getElementById("peek-auction");
      if (peek) {
        peek.textContent = snaps.length ? `${snaps.length} 只监测中` : "";
        peek.hidden = !snaps.length;
      }
    } catch (_) {
      if (empty) empty.hidden = false;
    }
  }

  async function loadLive() {
    if (!api()?.isOnline()) return;
    try {
      const alerts = await api().fetch("/api/alerts");
      alertCount = alerts.unread_count || 0;
      const unread = document.getElementById("alert-unread");
      if (unread) unread.textContent = String(alertCount);
      layout()?.updateAlertBadges(alertCount);
      const feed = document.getElementById("alert-feed");
      if (feed && UI()) feed.innerHTML = (alerts.alerts || []).slice(0, 20).map((a) => UI().renderAlertCard(a, stockHref(a.code))).join("");
      const pool = await api().fetch("/api/recommendations/today");
      const el = document.getElementById("live-pool");
      if (el && UI()) el.innerHTML = (pool.sectors || []).map((sec) => UI().renderPoolSector(sec, (c) => stockHref(c))).join("");
      updatePeekSummaries();
    } catch (_) {}
  }

  async function loadReview() {
    const data = await fetchJson("/api/review/today", "../data/review.json");
    reviewCache = data;
    const line = document.getElementById("review-summary-line");
    const box = document.getElementById("review-summary");
    if (!data) {
      if (line) line.textContent = "暂无复盘";
      return;
    }
    const rate = ((data.hit_rate || 0) * 100).toFixed(1);
    if (line) line.textContent = `命中率 ${rate}%`;
    if (box && UI()) box.innerHTML = UI().renderReviewStats(data);
    const hits = document.getElementById("review-hits");
    const missed = document.getElementById("review-missed");
    if (hits && UI()) hits.innerHTML = (data.hits || []).map((h) => `<li><a href="${stockHref(h.code)}">${UI().esc(h.code)} ${UI().esc(h.name)}</a> <span class="change-up">+${h.change_pct}%</span></li>`).join("");
    if (missed && UI()) missed.innerHTML = (data.missed_top || []).map((m) => `<li><a href="${stockHref(m.code)}">${UI().esc(m.code)} ${UI().esc(m.name)}</a> <span class="change-up">+${m.change_pct}%</span></li>`).join("");
    updatePeekSummaries();
  }

  async function loadPositions() {
    const el = document.getElementById("pos-list");
    if (!el) return;
    if (!api()?.isOnline()) {
      el.innerHTML = "<p class=\"empty-hint\">连接 API 后可管理仓位</p>";
      return;
    }
    const data = await api().fetch("/api/positions");
    if (!UI()) return;
    el.innerHTML = (data.positions || []).map((p) => UI().renderPosCard(p, { withClose: true })).join("") ||
      "<p class=\"empty-hint\">暂无持仓</p>";
    el.querySelectorAll(".pos-close").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await fetch(`${api().base}/api/positions/${btn.dataset.id}`, { method: "DELETE" });
        loadPositions();
      });
    });
  }

  async function submitPosition(payload) {
    if (!api()?.isOnline()) return;
    await fetch(`${api().base}/api/positions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    loadPositions();
  }

  function renderWatchlistCards(data) {
    const grid = document.getElementById("stock-grid");
    const tbody = document.querySelector("#stock-table tbody");
    if (!grid || !UI()) return;
    const stocks = data.stocks || [];
    grid.innerHTML = stocks.map((s) => UI().renderStockCard(s, { href: stockHref(s.code) })).join("");
    if (tbody) tbody.innerHTML = stocks.map((s) => UI().renderStockTableRow(s, stockHref(s.code))).join("");
    initCompareSelects();
    applyWatchlistFilters();
  }

  function renderBreadth(data) {
    const el = document.getElementById("breadth-summary");
    if (!el || !UI()) return;
    el.innerHTML = UI().renderSignalDashboard({
      market: data.market,
      breadth: data.breadth,
      counts: UI().countSignals(data.stocks),
    });
  }

  function applyWatchlistFilters() {
    const grid = document.getElementById("stock-grid");
    const q = (document.getElementById("filter-search")?.value || "").trim().toLowerCase();
    const sig = document.getElementById("filter-signal")?.value || "";
    const sort = document.getElementById("filter-sort")?.value || "score";
    const bucket = UI()?.signalBucket;
    if (!bucket) return;
    const links = grid ? [...grid.querySelectorAll(".stock-card-link")] : [];
    links.forEach((el) => {
      const code = el.dataset.code || "";
      const name = el.dataset.name || "";
      const matchQ = !q || code.includes(q) || name.toLowerCase().includes(q);
      const matchSig = !sig || bucket(el.dataset.signal) === sig;
      el.style.display = matchQ && matchSig ? "" : "none";
    });
    const visible = links.filter((el) => el.style.display !== "none");
    visible.sort((a, b) => {
      if (sort === "code") return (a.dataset.code || "").localeCompare(b.dataset.code || "");
      if (sort === "confidence") return parseFloat(b.dataset.confidence || 0) - parseFloat(a.dataset.confidence || 0);
      return parseFloat(b.dataset.score || 0) - parseFloat(a.dataset.score || 0);
    });
    visible.forEach((el) => grid.appendChild(el));
    document.querySelectorAll("#stock-table tbody tr").forEach((row) => {
      const code = row.dataset.code || "";
      const name = row.dataset.name || "";
      const matchQ = !q || code.includes(q) || name.toLowerCase().includes(q);
      const matchSig = !sig || bucket(row.dataset.signal) === sig;
      row.style.display = matchQ && matchSig ? "" : "none";
    });
    const countEl = document.getElementById("stock-count");
    if (countEl) countEl.textContent = `(${visible.length} 只自选)`;
  }

  async function loadWatchlist() {
    let data;
    try {
      data = await fetch("../data/latest.json").then((r) => (r.ok ? r.json() : null));
    } catch (_) {}
    if (!data) return;
    updateHeaderMeta(data.meta);
    renderBreadth(data);
    renderWatchlistCards(data);
    if (api()?.isOnline()) {
      try {
        const q = await api().fetch("/api/quotes/intraday");
        (q.quotes || []).forEach((item) => {
          const el = document.querySelector(`.stock-card-link[data-code="${item.code}"]`);
          if (!el || item.change_pct == null) return;
          const chip = el.querySelector(".metric-chip.intraday .metric-chip-val");
          if (chip) {
            chip.textContent = `${item.change_pct >= 0 ? "+" : ""}${Number(item.change_pct).toFixed(2)}%`;
            chip.className = "metric-chip-val " + (item.change_pct >= 0 ? "change-up" : "change-down");
          }
        });
      } catch (_) {}
    }
  }

  function setPanelExpanded(panelId, expanded) {
    const panel = document.getElementById(panelId);
    if (!panel) return;
    const head = panel.querySelector(":scope > .cockpit-panel__head");
    const body = panel.querySelector(":scope > .cockpit-panel__body");
    panel.classList.toggle("cockpit-panel--active", expanded);
    panel.classList.toggle("cockpit-panel--collapsed", !expanded);
    if (head) head.setAttribute("aria-expanded", expanded ? "true" : "false");
    if (body) body.hidden = !expanded;
  }

  const TOP_PANELS = ["panel-digest", "panel-auction", "panel-live", "panel-review"];

  function updatePanelFocus(panelId) {
    TOP_PANELS.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const isFocus = id === panelId || (panelId === "panel-pool" && id === "panel-digest");
      el.classList.toggle("cockpit-panel--focus", isFocus);
      el.classList.toggle("cockpit-panel--peek", !isFocus);
    });
    const poolEl = document.getElementById("panel-pool");
    if (poolEl) poolEl.classList.toggle("cockpit-panel--focus", panelId === "panel-pool");
  }

  function setTimelineActive(panelId) {
    document.querySelectorAll(".journey-timeline__step").forEach((c) => {
      c.classList.toggle("journey-timeline__step--active", c.dataset.panel === panelId);
    });
  }

  function scrollToPanel(panelId) {
    if (!panelId) return;

    if (panelId === "panel-pool") {
      setPanelExpanded("panel-digest", true);
      setPanelExpanded("panel-pool", true);
      TOP_PANELS.forEach((id) => { if (id !== "panel-digest") setPanelExpanded(id, false); });
    } else if (TOP_PANELS.includes(panelId)) {
      setPanelExpanded(panelId, true);
      TOP_PANELS.forEach((id) => { if (id !== panelId) setPanelExpanded(id, false); });
      if (panelId !== "panel-digest") setPanelExpanded("panel-pool", false);
    }

    setTimelineActive(panelId);
    updatePanelFocus(panelId);

    const scrollTarget = document.getElementById(panelId);
    if (scrollTarget) {
      requestAnimationFrame(() => {
        scrollTarget.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  function applySessionUI(session) {
    currentSession = session || "pre_market";
    const primary = SESSION_PANEL[currentSession] || "panel-digest";
    setPanelExpanded("panel-digest", ["pre_market", "auction", "lunch", "closed"].includes(currentSession));
    setPanelExpanded("panel-auction", currentSession === "auction");
    setPanelExpanded("panel-live", ["morning", "afternoon", "lunch"].includes(currentSession));
    setPanelExpanded("panel-review", ["post_market", "closed"].includes(currentSession));
    setPanelExpanded("panel-pool", ["pre_market", "auction"].includes(currentSession));
    TOP_PANELS.forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      const isFocus = id === primary || (id === "panel-digest" && primary === "panel-pool");
      el.classList.toggle("cockpit-panel--focus", isFocus);
      el.classList.toggle("cockpit-panel--peek", !isFocus);
    });
    const poolEl = document.getElementById("panel-pool");
    if (poolEl) poolEl.classList.toggle("cockpit-panel--focus", primary === "panel-pool");
    const TIMELINE_ACTIVE = {
      pre_market: "panel-digest",
      auction: "panel-auction",
      morning: "panel-live",
      lunch: "panel-live",
      afternoon: "panel-live",
      post_market: "panel-review",
      closed: "panel-review",
    };
    setTimelineActive(TIMELINE_ACTIVE[currentSession] || "panel-digest");
    updatePeekSummaries();
    if (layout()?.isMobile()) {
      const scrollId = primary === "panel-pool" ? "panel-pool" : primary;
      const target = document.getElementById(scrollId);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function onSessionUpdate(data) {
    updateHero(data?.session || "pre_market", data);
    applySessionUI(data?.session);
  }

  function initAccordions() {
    document.querySelectorAll(".cockpit-panel > .cockpit-panel__head").forEach((head) => {
      head.addEventListener("click", () => {
        const panel = head.closest(".cockpit-panel");
        setPanelExpanded(panel.id, head.getAttribute("aria-expanded") !== "true");
      });
    });
    document.querySelectorAll(".journey-timeline__step").forEach((chip) => {
      chip.addEventListener("click", () => scrollToPanel(chip.dataset.panel));
    });
    document.getElementById("session-cta")?.addEventListener("click", () => {
      scrollToPanel(SESSION_PANEL[currentSession] || "panel-digest");
    });
  }

  function initViewToggle() {
    const grid = document.getElementById("stock-grid");
    const table = document.getElementById("table-view");
    const btnCards = document.getElementById("btn-view-cards");
    const btnTable = document.getElementById("btn-view-table");
    function setView(isTable) {
      grid?.classList.toggle("table-hidden", isTable);
      table?.classList.toggle("active", isTable);
      btnCards?.classList.toggle("active", !isTable);
      btnTable?.classList.toggle("active", isTable);
      localStorage.setItem("nexstrat-view", isTable ? "table" : "cards");
    }
    if (localStorage.getItem("nexstrat-view") === "table") setView(true);
    btnCards?.addEventListener("click", () => setView(false));
    btnTable?.addEventListener("click", () => setView(true));
  }

  function updateCompare() {
    const compareList = document.getElementById("compare-list");
    const compareCount = document.getElementById("compare-count");
    const comparePanel = document.getElementById("compare-panel");
    if (!compareList || !UI()) return;
    if (compareCount) compareCount.textContent = `(${compareStocks.length})`;
    if (!compareStocks.length) {
      compareList.innerHTML = "<div class=\"empty-hint\">点击卡片左上角复选框添加对比</div>";
      comparePanel?.classList.remove("active");
      return;
    }
    comparePanel?.classList.add("active");
    compareList.innerHTML = compareStocks.map((s) => {
      const score = s.score || 0;
      const color = score > 0.2 ? "#22C55E" : score < -0.2 ? "#EF4444" : "#94A3B8";
      const width = ((score + 1) / 2 * 100).toFixed(0);
      return `<div class="compare-item"><div><span class="compare-item-code">${UI().esc(s.code)}</span> <span class="compare-item-name">${UI().esc(s.name)}</span><div class="compare-bar"><div class="compare-bar-fill" style="width:${width}%;background:${color}"></div></div></div><span class="compare-item-remove" data-code="${UI().esc(s.code)}">×</span></div>`;
    }).join("");
    compareList.querySelectorAll(".compare-item-remove").forEach((btn) => {
      btn.addEventListener("click", () => {
        compareStocks = compareStocks.filter((s) => s.code !== btn.dataset.code);
        document.querySelectorAll(`.stock-select[data-code="${btn.dataset.code}"]`).forEach((el) => el.classList.remove("checked"));
        updateCompare();
      });
    });
  }

  function initCompareSelects() {
    document.querySelectorAll(".stock-select").forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = "1";
      el.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const card = el.closest(".stock-card-link");
        if (!card) return;
        const code = el.dataset.code;
        const idx = compareStocks.findIndex((s) => s.code === code);
        if (idx >= 0) {
          compareStocks.splice(idx, 1);
          el.classList.remove("checked");
        } else if (compareStocks.length < 4) {
          compareStocks.push({ code, name: card.dataset.name, score: parseFloat(card.dataset.score) || 0 });
          el.classList.add("checked");
        }
        updateCompare();
      });
    });
    const closeBtn = document.getElementById("compare-close");
    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.dataset.bound = "1";
      closeBtn.addEventListener("click", () => {
        compareStocks = [];
        document.querySelectorAll(".stock-select.checked").forEach((el) => el.classList.remove("checked"));
        updateCompare();
      });
    }
  }

  function initPositionsForms() {
    document.getElementById("pos-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await submitPosition({
        code: document.getElementById("pos-code").value,
        name: document.getElementById("pos-name").value,
        shares: +document.getElementById("pos-shares").value,
        entry_price: +document.getElementById("pos-price").value,
      });
      e.target.reset();
    });
    document.getElementById("pos-form-m")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      await submitPosition({
        code: document.getElementById("pos-code-m").value,
        name: "",
        shares: +document.getElementById("pos-shares-m").value,
        entry_price: +document.getElementById("pos-price-m").value,
      });
      e.target.reset();
      document.getElementById("pos-form-mobile").hidden = true;
    });
    document.getElementById("pos-fab")?.addEventListener("click", () => {
      const m = document.getElementById("pos-form-mobile");
      if (m) m.hidden = !m.hidden;
    });
  }

  function initWatchlistFilters() {
    document.getElementById("filter-search")?.addEventListener("input", applyWatchlistFilters);
    document.getElementById("filter-signal")?.addEventListener("change", applyWatchlistFilters);
    document.getElementById("filter-sort")?.addEventListener("change", applyWatchlistFilters);
    document.getElementById("filter-toggle")?.addEventListener("click", () => {
      const d = document.getElementById("filter-drawer");
      const btn = document.getElementById("filter-toggle");
      if (!d) return;
      d.hidden = !d.hidden;
      btn?.setAttribute("aria-expanded", d.hidden ? "false" : "true");
    });
  }

  async function refreshSessionAndApply() {
    if (api()?.isOnline()) {
      try {
        onSessionUpdate(await api().fetch("/api/market/session"));
        return;
      } catch (_) {}
    }
    onSessionUpdate({ session: "pre_market" });
  }

  function initPolls() {
    const poll = live()?.startPoll;
    if (!poll) return;
    poll(loadDigest, 300000);
    poll(loadPool, 60000);
    poll(loadAuction, 60000, () => ["auction", "pre_market"].includes(currentSession));
    poll(loadLive, 120000, () => ["morning", "afternoon", "lunch"].includes(currentSession));
    poll(refreshSessionAndApply, 60000);
    poll(() => live()?.refreshAlertBadge(), 120000);
  }

  async function initCockpit() {
    if (!window.StockCopilotUI) return;
    initAccordions();
    initPositionsForms();
    initWatchlistFilters();
    initViewToggle();
    updateHero("pre_market", {});
    await Promise.all([loadDigest(), loadPool(), loadAuction(), loadLive(), loadReview()]);
    try {
      const meta = await fetch("../data/latest.json").then((r) => (r.ok ? r.json() : null));
      if (meta?.meta) updateHeaderMeta(meta.meta);
    } catch (_) {}
    await refreshSessionAndApply();
    initPolls();
  }

  window.StockCopilotCockpit = {
    loadDigest, loadPool, loadAuction, loadLive, loadReview, loadPositions, loadWatchlist,
    scrollToPanel, applySessionUI, initCockpit, updateHero,
  };

  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("cockpit-root")) initCockpit();
  });
})();
