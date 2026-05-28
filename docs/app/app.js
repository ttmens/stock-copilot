(function () {
  "use strict";

  const cfg = window.STOCK_COPILOT || {};
  const API = (cfg.API_BASE || "").replace(/\/$/, "");

  function signalBucket(signal) {
    const s = (signal || "").toLowerCase();
    if (s.includes("buy") || s === "bullish" || s === "strong_buy") return "bullish";
    if (s.includes("sell") || s === "bearish" || s === "strong_sell") return "bearish";
    return "hold";
  }

  function priceColorClass(value) {
    if (value == null || Number.isNaN(value)) return "";
    return value >= 0 ? "change-up" : "change-down";
  }

  function applyFilters() {
    const grid = document.getElementById("stock-grid");
    const q = (document.getElementById("filter-search")?.value || "").trim().toLowerCase();
    const sig = document.getElementById("filter-signal")?.value || "";
    const sort = document.getElementById("filter-sort")?.value || "score";

    const links = grid ? [...grid.querySelectorAll(".stock-card-link")] : [];
    links.forEach((el) => {
      const code = el.dataset.code || "";
      const name = el.dataset.name || "";
      const bucket = signalBucket(el.dataset.signal);
      const matchQ = !q || code.includes(q) || name.toLowerCase().includes(q);
      const matchSig = !sig || bucket === sig;
      el.style.display = matchQ && matchSig ? "" : "none";
    });

    const visible = links.filter((el) => el.style.display !== "none");
    visible.sort((a, b) => {
      if (sort === "code") return (a.dataset.code || "").localeCompare(b.dataset.code || "");
      if (sort === "confidence") {
        return parseFloat(b.dataset.confidence || 0) - parseFloat(a.dataset.confidence || 0);
      }
      return parseFloat(b.dataset.score || 0) - parseFloat(a.dataset.score || 0);
    });
    if (grid) {
      visible.forEach((el) => grid.appendChild(el));
    }

    const tableRows = [...document.querySelectorAll("#stock-table tbody tr")];
    tableRows.forEach((row) => {
      const code = row.dataset.code || "";
      const name = row.dataset.name || "";
      const bucket = signalBucket(row.dataset.signal);
      const matchQ = !q || code.includes(q) || name.toLowerCase().includes(q);
      const matchSig = !sig || bucket === sig;
      row.style.display = matchQ && matchSig ? "" : "none";
    });

    const countEl = document.getElementById("stock-count");
    if (countEl) countEl.textContent = `(${visible.length} 只自选)`;
  }

  async function mergeIntraday() {
    if (!API) return;
    try {
      const res = await fetch(`${API}/api/quotes/intraday`);
      if (!res.ok) return;
      const data = await res.json();
      const quotes = data.quotes || [];
      quotes.forEach((q) => {
        const el = document.querySelector(`.stock-card-link[data-code="${q.code}"]`);
        if (!el) return;
        const chip = el.querySelector(".metric-chip.intraday");
        if (chip && q.change_pct != null) {
          const val = chip.querySelector(".metric-chip-val");
          if (val) {
            val.textContent = `${q.change_pct >= 0 ? "+" : ""}${Number(q.change_pct).toFixed(2)}%`;
            val.className = "metric-chip-val " + priceColorClass(Number(q.change_pct));
          }
        }
      });
    } catch (_) {
      /* static-only mode */
    }
  }

  async function cacheLatestJson() {
    try {
      const res = await fetch("data/latest.json");
      if (!res.ok) return;
      const data = await res.json();
      localStorage.setItem("stock_copilot_latest", JSON.stringify(data));
    } catch (_) {}
  }

  function showEmptyState() {
    const grid = document.getElementById("stock-grid");
    if (!grid) return;
    const allCards = [...grid.querySelectorAll(".stock-card-link")];
    if (!allCards.length) return;
    const allHidden = allCards.every(c => c.style.display === "none");
    let emptyEl = grid.querySelector(".empty-state");
    if (allHidden) {
      if (!emptyEl) {
        emptyEl = document.createElement("div");
        emptyEl.className = "empty-state";
        emptyEl.innerHTML = '<div class="empty-state-icon">📭</div><div class="empty-state-text">暂无匹配的股票</div><div class="empty-state-sub">尝试调整筛选条件</div>';
        grid.appendChild(emptyEl);
      }
    } else if (emptyEl) {
      emptyEl.remove();
    }
  }

  async function loadPublishedMeta() {
    if (!API) return;
    try {
      const res = await fetch(`${API}/api/published`);
      if (!res.ok) return;
      const data = await res.json();
      const ts = data.db?.published_at || data.file?.published_at;
      if (ts) {
        const meta = document.querySelector(".header-meta");
        if (meta && !meta.dataset.enriched) {
          meta.dataset.enriched = "1";
          meta.textContent += ` · 发布 ${String(ts).slice(0, 16).replace("T", " ")}`;
        }
      }
    } catch (_) {}
  }

  document.getElementById("filter-search")?.addEventListener("input", applyFilters);
  document.getElementById("filter-signal")?.addEventListener("change", applyFilters);
  document.getElementById("filter-sort")?.addEventListener("change", applyFilters);

  // Override applyFilters to also show empty state
  const _origApply = applyFilters;
  function applyFiltersWithEmpty() {
    _origApply();
    showEmptyState();
  }
  // Re-bind
  document.getElementById("filter-search")?.removeEventListener("input", applyFilters);
  document.getElementById("filter-signal")?.removeEventListener("change", applyFilters);
  document.getElementById("filter-sort")?.removeEventListener("change", applyFilters);
  document.getElementById("filter-search")?.addEventListener("input", applyFiltersWithEmpty);
  document.getElementById("filter-signal")?.addEventListener("change", applyFiltersWithEmpty);
  document.getElementById("filter-sort")?.addEventListener("change", applyFiltersWithEmpty);

  applyFiltersWithEmpty();
  cacheLatestJson();
  mergeIntraday();
  loadPublishedMeta();
})();
