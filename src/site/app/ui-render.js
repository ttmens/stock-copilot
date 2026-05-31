/** Shared UI render helpers — mirrors generator.py TPL_HOME card structure */
(function () {
  "use strict";

  function esc(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function signalBucket(signal) {
    const s = (signal || "").toLowerCase();
    if (s.includes("buy") || s === "bullish" || s === "strong_buy") return "bullish";
    if (s.includes("sell") || s === "bearish" || s === "strong_sell") return "bearish";
    return "hold";
  }

  function badgeClass(sentiment) {
    const b = signalBucket(sentiment);
    return b === "bullish" ? "bullish" : b === "bearish" ? "bearish" : "hold";
  }

  function scoreClasses(score) {
    const s = Number(score) || 0;
    if (s > 0.2) return { scoreCls: "signal-score-bull", barCls: "signal-bar-bull" };
    if (s < -0.2) return { scoreCls: "signal-score-bear", barCls: "signal-bar-bear" };
    return { scoreCls: "signal-score-hold", barCls: "signal-bar-hold" };
  }

  function confDots(confidence) {
    const filled = Math.floor((Number(confidence) || 0) * 5);
    let html = "";
    for (let i = 0; i < 5; i++) {
      html += `<span class="conf-dot${i < filled ? " filled" : ""}"></span>`;
    }
    return html;
  }

  function maLabel(v) {
    return { bullish: "多头", bearish: "空头", neutral: "交叉" }[v] || v || "—";
  }

  function renderStockCard(stock, opts) {
    opts = opts || {};
    const href = opts.href || `stock.html?code=${stock.code}`;
    const compact = opts.compact === true;
    const withSelect = opts.withSelect !== false && !compact;
    const score = stock.signal_breakdown?.final_score ?? stock.score ?? 0;
    const { scoreCls, barCls } = scoreClasses(score);
    const barWidth = ((Number(score) + 1) / 2 * 100).toFixed(1);
    const conf = Number(stock.confidence) || 0;
    const sb = stock.signal_breakdown || {};
    const flags = sb.contradiction_flags || [];

    if (compact) {
      const stale = stock.source === "auction" ? " stale-chip" : "";
      return `<a class="symbol-link pool-stock-card--compact stock-card${stale}" href="${esc(href)}">` +
        `<div class="card-stock-code">${esc(stock.code)}</div>` +
        `<div class="card-stock-name">${esc(stock.name)}</div>` +
        `<div class="decision-bar-track"><div class="decision-bar-fill ${barCls}" style="width:${barWidth}%"></div></div>` +
        `<div class="metric-chip-val ${scoreCls}">${Number(score).toFixed(2)}</div></a>`;
    }

    let extraBadges = "";
    if (stock.consensus_score != null) {
      const cs = Number(stock.consensus_score);
      const label = cs >= 0.8 ? "高共识" : cs >= 0.5 ? "中共识" : "低共识";
      const color = cs >= 0.8 ? "#22C55E" : cs >= 0.5 ? "#F59E0B" : "#EF4444";
      extraBadges += `<span class="consensus-badge" style="color:${color}">🤖 ${label} ${Math.round(cs * 100)}%</span>`;
    }
    if (flags.length) {
      extraBadges += `<span class="contradiction-badge" title="信号冲突">⚠️ 冲突×${flags.length}</span>`;
    }

    let metrics = "";
    if (stock.momentum_5d != null) {
      const cls = stock.momentum_5d > 0 ? "change-up" : stock.momentum_5d < 0 ? "change-down" : "";
      metrics += `<div class="metric-chip"><span class="metric-chip-label">5日</span><span class="metric-chip-val ${cls}">${stock.momentum_5d >= 0 ? "+" : ""}${Number(stock.momentum_5d).toFixed(1)}%</span></div>`;
    }
    if (stock.ma_alignment) {
      const mac = stock.ma_alignment === "bullish" ? "signal-score-bull" : stock.ma_alignment === "bearish" ? "signal-score-bear" : "signal-score-hold";
      metrics += `<div class="metric-chip"><span class="metric-chip-label">均线</span><span class="metric-chip-val ${mac}">${maLabel(stock.ma_alignment)}</span></div>`;
    }
    metrics += `<div class="metric-chip intraday"><span class="metric-chip-label">日内</span><span class="metric-chip-val">—</span></div>`;
    if (stock.volume_ratio != null) {
      metrics += `<div class="metric-chip"><span class="metric-chip-label">量比</span><span class="metric-chip-val">${Number(stock.volume_ratio).toFixed(2)}</span></div>`;
    }
    if (stock.pe_ttm != null) {
      metrics += `<div class="metric-chip"><span class="metric-chip-label">PE</span><span class="metric-chip-val">${Number(stock.pe_ttm).toFixed(1)}</span></div>`;
    }

    let basis = "";
    if (stock.key_basis && stock.key_basis.length) {
      basis = "<ul class=\"key-basis-list\">" + stock.key_basis.slice(0, 3).map((i) => `<li>${esc(i)}</li>`).join("") + "</ul>";
    }

    let accordion = "";
    const tech = stock.technical?.summary;
    const fund = stock.fundamental?.summary;
    const cap = stock.capital?.summary;
    if (tech || fund || cap) {
      accordion = "<details class=\"card-accordion\"><summary>展开摘要</summary><div class=\"card-accordion-body\">";
      if (tech) accordion += `<p><strong>技术</strong> ${esc(tech.slice(0, 120))}${tech.length > 120 ? "…" : ""}</p>`;
      if (fund) accordion += `<p><strong>基本面</strong> ${esc(fund.slice(0, 120))}${fund.length > 120 ? "…" : ""}</p>`;
      if (cap) accordion += `<p><strong>资金</strong> ${esc(cap.slice(0, 120))}${cap.length > 120 ? "…" : ""}</p>`;
      accordion += "</div></details>";
    }

    const risk = stock.risk_points && stock.risk_points.length
      ? `<div class="risk-block">⚠ ${esc(stock.risk_points[0])}</div>` : "";

    const selectEl = withSelect ? `<div class="stock-select" data-code="${esc(stock.code)}" title="加入对比"></div>` : "";

    return `<div class="stock-card-link" data-code="${esc(stock.code)}" data-name="${esc(stock.name)}" data-signal="${esc(stock.overall_sentiment)}" data-score="${score}" data-confidence="${conf}">` +
      `<div class="stock-card">` +
      `<div class="card-header">` +
      `<a href="${esc(href)}" class="card-title-link">${selectEl}<div><div class="card-stock-code">${esc(stock.code)}</div><div class="card-stock-name">${esc(stock.name)}</div></div></a>` +
      `<span class="signal-badge ${badgeClass(stock.overall_sentiment)}">${esc(stock.overall_focus || "—")}</span>${extraBadges}` +
      `</div>` +
      `<div class="decision-card">` +
      `<div class="decision-score-row"><span class="decision-score-label">综合评分</span><span class="decision-score-value ${scoreCls}">${score >= 0 ? "+" : ""}${Number(score).toFixed(3)}</span></div>` +
      `<div class="decision-bar-track"><div class="decision-bar-fill ${barCls}" style="width:${barWidth}%"></div></div>` +
      `<div class="decision-confidence"><span>置信度</span><div class="conf-dots">${confDots(conf)}</div><span class="conf-value">${Math.round(conf * 100)}%</span></div>` +
      `</div>` +
      (stock.overall_summary ? `<p class="card-summary">${esc(stock.overall_summary.slice(0, 120))}${stock.overall_summary.length > 120 ? "…" : ""}</p>` : "") +
      basis +
      `<div class="metrics-row">${metrics}</div>` +
      accordion + risk +
      `<a href="${esc(href)}" class="card-detail-link">查看详情 →</a>` +
      `</div></div>`;
  }

  function renderStockTableRow(stock, href) {
    const score = stock.signal_breakdown?.final_score ?? 0;
    const { scoreCls } = scoreClasses(score);
    href = href || `stock.html?code=${stock.code}`;
    return `<tr data-code="${esc(stock.code)}" data-name="${esc(stock.name)}" data-signal="${esc(stock.overall_sentiment)}" data-score="${score}" data-confidence="${stock.confidence || 0}">` +
      `<td class="stock-code"><a href="${esc(href)}" class="stock-code-link">${esc(stock.code)}</a></td>` +
      `<td>${esc(stock.name)}</td>` +
      `<td><span class="signal-badge ${badgeClass(stock.overall_sentiment)}">${esc(stock.overall_focus || "—")}</span></td>` +
      `<td class="${scoreCls}">${score >= 0 ? "+" : ""}${Number(score).toFixed(3)}</td>` +
      `<td>${Math.round((stock.confidence || 0) * 100)}%</td></tr>`;
  }

  function renderBreadthWidget(breadth) {
    if (!breadth) return "";
    const color = breadth.color || "#94A3B8";
    return `<div class="breadth-widget">` +
      `<span class="breadth-label">市场广度</span>` +
      `<span class="breadth-score" style="color:${esc(color)}">${esc(breadth.score ?? 50)}</span>` +
      `<span class="breadth-zone" style="color:${esc(color)}">${esc(breadth.zone_label || breadth.zone || "")}</span>` +
      `<span class="breadth-exposure">建议仓位 ${esc(breadth.recommended_exposure || "")}</span></div>`;
  }

  function renderSignalDashboard(data) {
    data = data || {};
    const market = data.market;
    const breadth = data.breadth;
    const counts = data.counts || { bullish: 0, hold: 0, bearish: 0 };
    const total = counts.bullish + counts.hold + counts.bearish;
    let head = "";
    if (market && market.close != null) {
      const ch = Number(market.change_pct) || 0;
      const chCls = ch >= 0 ? "change-up" : "change-down";
      head += `<div class="signal-dashboard-head"><div>` +
        `<span class="signal-dashboard-label">市场温度</span>` +
        `<span class="signal-dashboard-value">${esc(market.index_name || "指数")} ${Number(market.close).toFixed(2)}</span>` +
        `<span class="signal-dashboard-change ${chCls}">${ch >= 0 ? "+" : ""}${ch.toFixed(2)}%</span></div>` +
        renderBreadthWidget(breadth) + `</div>`;
    } else if (breadth) {
      head += `<div class="signal-dashboard-head">${renderBreadthWidget(breadth)}</div>`;
    }
    let bar = "";
    if (total > 0) {
      bar = `<div class="signal-bar">` +
        (counts.bullish ? `<div class="signal-bar-seg bull" style="width:${Math.round(counts.bullish / total * 100)}%"></div>` : "") +
        (counts.hold ? `<div class="signal-bar-seg hold" style="width:${Math.round(counts.hold / total * 100)}%"></div>` : "") +
        (counts.bearish ? `<div class="signal-bar-seg bear" style="width:${Math.round(counts.bearish / total * 100)}%"></div>` : "") +
        `</div><div class="signal-legend">` +
        `<span class="signal-legend-item"><span class="signal-legend-dot bull"></span> 看多 ${counts.bullish}</span>` +
        `<span class="signal-legend-item"><span class="signal-legend-dot hold"></span> 观望 ${counts.hold}</span>` +
        `<span class="signal-legend-item"><span class="signal-legend-dot bear"></span> 看空 ${counts.bearish}</span></div>`;
    }
    return head + bar;
  }

  function renderHotEvent(event) {
    return `<div class="event-card"><span class="event-card-rank">#${esc(event.rank || "")}</span><span class="event-card-title">${esc(event.title || "")}</span></div>`;
  }

  function renderReviewStats(review) {
    if (!review) return "";
    const rate = ((review.hit_rate || 0) * 100).toFixed(1);
    const deg = Math.round((review.hit_rate || 0) * 360);
    return `<div class="review-stat-grid">` +
      `<div class="hit-rate-ring" style="--hit-deg:${deg}deg"><span class="hit-rate-value">${rate}%</span><span class="hit-rate-label">命中率</span></div>` +
      `<div class="review-stat-cards">` +
      `<div class="review-stat-card"><span class="review-stat-num">${review.hit_count || 0}</span><span class="review-stat-label">命中</span></div>` +
      `<div class="review-stat-card"><span class="review-stat-num">${review.miss_count || 0}</span><span class="review-stat-label">遗漏</span></div>` +
      `</div></div>`;
  }

  function renderPoolSector(sector, stockHrefFn) {
    stockHrefFn = stockHrefFn || ((c) => `stock.html?code=${c}`);
    let html = `<div class="pool-sector"><h3>${esc(sector.name || "")}</h3><div class="pool-grid">`;
    (sector.stocks || []).forEach((s) => {
      html += renderStockCard({ ...s, score: s.score }, { href: stockHrefFn(s.code), compact: true });
    });
    html += "</div></div>";
    return html;
  }

  function renderAlertCard(alert, href) {
    href = href || `stock.html?code=${alert.code}`;
    return `<div class="alert-card severity-${esc(alert.severity || "info")}">` +
      `<a href="${esc(href)}">${esc(alert.code)} ${esc(alert.name || "")}</a>` +
      `<div>${esc(alert.message || "")}</div>` +
      `<small>${esc(alert.created_at || "")}</small></div>`;
  }

  function renderAuctionRow(snap, opts) {
    opts = opts || {};
    const href = opts.href || `stock.html?code=${snap.code}`;
    if (opts.mobile) {
      return `<a class="cockpit-mobile-card alert-card" href="${esc(href)}"><strong>${esc(snap.code)}</strong> 量比 ${snap.volume_ratio ?? "—"} · 偏离 ${snap.price_deviation ?? "—"}</a>`;
    }
    return `<tr><td><a href="${esc(href)}">${esc(snap.code)}</a></td><td>${snap.volume_ratio ?? "—"}</td><td>${snap.price_deviation ?? "—"}</td><td>${snap.cancel_rate ?? "—"}</td></tr>`;
  }

  function renderPosCard(pos, opts) {
    opts = opts || {};
    return `<div class="pos-card">` +
      `<div class="pos-card-main"><strong class="pos-card-code">${esc(pos.code)}</strong> <span class="pos-card-name">${esc(pos.name || "")}</span>` +
      `<div class="pos-card-detail">${pos.shares} 股 @ ${pos.entry_price}</div></div>` +
      (opts.withClose ? `<button type="button" class="pos-close" data-id="${pos.id}">平仓</button>` : "") +
      `</div>`;
  }

  function countSignals(stocks) {
    const counts = { bullish: 0, hold: 0, bearish: 0 };
    (stocks || []).forEach((s) => {
      counts[signalBucket(s.overall_sentiment)]++;
    });
    return counts;
  }

  window.StockCopilotUI = {
    esc,
    signalBucket,
    badgeClass,
    scoreClasses,
    renderStockCard,
    renderStockTableRow,
    renderSignalDashboard,
    renderBreadthWidget,
    renderHotEvent,
    renderReviewStats,
    renderPoolSector,
    renderAlertCard,
    renderAuctionRow,
    renderPosCard,
    countSignals,
  };
})();
