/** Shared layout — tab routing, mobile/desktop nav sync */
(function () {
  "use strict";

  const TABS = ["today", "watchlist", "me"];
  let activeTab = "today";

  function isMobile() {
    return window.matchMedia("(max-width: 899px)").matches;
  }

  function setActiveTab(tab) {
    if (!TABS.includes(tab)) tab = "today";
    activeTab = tab;
    document.querySelectorAll(".tab-pane").forEach((el) => {
      el.classList.toggle("tab-pane--hidden", el.dataset.tab !== tab);
    });
    document.querySelectorAll("[data-nav-tab]").forEach((el) => {
      el.classList.toggle("active", el.dataset.navTab === tab);
    });
    if (location.hash !== "#" + tab) {
      history.replaceState(null, "", "#" + tab);
    }
    if (tab === "watchlist" && window.StockCopilotCockpit?.loadWatchlist) {
      window.StockCopilotCockpit.loadWatchlist();
    }
    if (tab === "me" && window.StockCopilotCockpit?.loadPositions) {
      window.StockCopilotCockpit.loadPositions();
    }
  }

  function parseHash() {
    const h = (location.hash || "#today").replace("#", "");
    if (h === "me" || h === "positions") return "me";
    if (h === "watchlist") return "watchlist";
    return "today";
  }

  function initNav() {
    document.querySelectorAll("[data-nav-tab]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        setActiveTab(el.dataset.navTab);
      });
    });
    window.addEventListener("hashchange", () => setActiveTab(parseHash()));
    setActiveTab(parseHash());
  }

  function updateAlertBadges(count) {
    document.querySelectorAll(".alert-badge").forEach((b) => {
      b.textContent = count;
      b.hidden = !count;
    });
  }

  window.StockCopilotLayout = {
    initNav,
    setActiveTab,
    isMobile,
    updateAlertBadges,
  };

  document.addEventListener("DOMContentLoaded", initNav);
})();
