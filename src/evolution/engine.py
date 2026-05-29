"""EvolutionEngine — orchestrates the full OODA self-evolving loop.

Observe → Orient → Decide → Act

Usage:
    from src.evolution import EvolutionEngine
    engine = EvolutionEngine()
    report = engine.run_cycle()
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EvolutionReport:
    """Full evolution cycle report."""
    cycle_id: str = ""
    date: str = ""
    phase: str = ""  # "observe" | "orient" | "decide" | "act" | "complete"

    # Performance
    win_rate: float = 0.0
    avg_return: float = 0.0
    sharpe_like: float = 0.0
    signals_verified: int = 0

    # Weights
    old_weights: dict = field(default_factory=dict)
    new_weights: dict = field(default_factory=dict)
    weights_changed: bool = False

    # Stock pool
    pool_size: int = 0
    evicted: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)

    # Diagnostics
    data_source_health: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    # Summary
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id,
            "date": self.date,
            "win_rate": round(self.win_rate, 4),
            "avg_return": round(self.avg_return, 4),
            "sharpe_like": round(self.sharpe_like, 4),
            "signals_verified": self.signals_verified,
            "old_weights": {k: round(v, 3) for k, v in self.old_weights.items()},
            "new_weights": {k: round(v, 3) for k, v in self.new_weights.items()},
            "weights_changed": self.weights_changed,
            "pool_size": self.pool_size,
            "evicted": self.evicted,
            "added": self.added,
            "data_source_health": self.data_source_health,
            "errors": self.errors,
            "summary": self.summary,
            "recommendations": self.recommendations,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# 🧬 系统进化报告",
            f"",
            f"**日期**: {self.date}",
            f"**周期ID**: {self.cycle_id}",
            f"",
            f"## 📊 绩效表现",
            f"",
            f"| 指标 | 值 |",
            f"|------|-----|",
            f"| 胜率 | {self.win_rate:.1%} |",
            f"| 平均收益 | {self.avg_return:.2f}% |",
            f"| 夏普比率 | {self.sharpe_like:.3f} |",
            f"| 验证信号数 | {self.signals_verified} |",
            f"",
        ]

        if self.weights_changed:
            lines.extend([
                f"## ⚖️ 权重调整",
                f"",
                f"| 信号层 | 旧权重 | 新权重 | 变化 |",
                f"|--------|--------|--------|------|",
            ])
            for k in self.old_weights:
                old = self.old_weights.get(k, 0)
                new = self.new_weights.get(k, 0)
                delta = new - old
                arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
                lines.append(f"| {k} | {old:.2f} | {new:.2f} | {delta:+.2f} {arrow} |")
            lines.append("")
        else:
            lines.extend([
                f"## ⚖️ 信号权重",
                f"",
                f"权重未调整（数据不足或已稳定）",
                f"",
                f"| 信号层 | 权重 |",
                f"|--------|------|",
            ])
            for k, v in self.new_weights.items():
                lines.append(f"| {k} | {v:.2f} |")
            lines.append("")

        if self.evicted or self.added:
            lines.extend([
                f"## 📋 股票池变动",
                f"",
                f"当前池大小: {self.pool_size}",
                f"",
            ])
            if self.evicted:
                lines.append(f"### 剔除 ({len(self.evicted)} 只)")
                for e in self.evicted:
                    lines.append(f"- **{e['code']}** {e.get('name', '')}: {e.get('reason', '')}")
                lines.append("")
            if self.added:
                lines.append(f"### 新增 ({len(self.added)} 只)")
                for a in self.added:
                    lines.append(f"- **{a['code']}** {a.get('name', '')}: {a.get('reason', '')}")
                lines.append("")

        if self.summary:
            lines.extend([
                f"## 📝 进化总结",
                f"",
                f"{self.summary}",
                f"",
            ])

        if self.recommendations:
            lines.extend([
                f"## 💡 建议",
                f"",
            ])
            for r in self.recommendations:
                lines.append(f"- {r}")
            lines.append("")

        lines.append(f"""---
*本报告由 Stock Copilot 自我进化系统自动生成*
*⚠️ 本系统仅供研究参考，不构成任何投资建议*""")

        return "\n".join(lines)


class EvolutionEngine:
    """Orchestrates the full OODA self-evolving loop."""

    def __init__(self, db=None):
        from src.evolution.tracker import PerformanceTracker
        from src.evolution.optimizer import WeightOptimizer
        from src.evolution.stock_pool import StockPoolManager
        from src.evolution.agent_tracker import AgentEvolutionTracker

        self.db = db
        self.tracker = PerformanceTracker()
        self.optimizer = WeightOptimizer()
        self.pool_manager = StockPoolManager(db=db)
        self.agent_tracker = AgentEvolutionTracker()  # D5
        self._cycle_count = 0

    def run_cycle(self, db=None) -> EvolutionReport:
        """Execute one full OODA evolution cycle.

        1. OBSERVE: verify yesterday's signals against actual prices
        2. ORIENT: analyze layer-level accuracy, compute metrics
        3. DECIDE: adjust weights, update stock pool
        4. ACT: apply new config, generate report, save to site
        """
        db = db or self.db
        self._cycle_count += 1
        report = EvolutionReport(
            cycle_id=f"evo-{self._cycle_count:04d}",
            date=date.today().isoformat(),
        )

        logger.info("=" * 60)
        logger.info("🧬 Evolution cycle %s starting...", report.cycle_id)
        logger.info("=" * 60)

        try:
            # Phase 1: OBSERVE
            report.phase = "observe"
            perf_report = self._observe(db)
            if perf_report:
                report.win_rate = perf_report.win_rate
                report.avg_return = perf_report.avg_return
                report.sharpe_like = perf_report.sharpe_like
                report.signals_verified = perf_report.verified
                logger.info("✅ Observe: %.1f%% win rate, %d signals verified",
                            perf_report.win_rate * 100, perf_report.verified)

                # Save performance to DB
                if db:
                    self.tracker.save_performance_report(db, perf_report)
            else:
                logger.warning("⚠️ No signals to verify (may need more data)")
                report.errors.append("无可验证信号，可能数据积累不足")

            # Phase 2: ORIENT + DECIDE (weights)
            report.phase = "orient"
            report.old_weights = dict(self.optimizer.get_weights())
            if perf_report and perf_report.verified > 0:
                report.new_weights = self.optimizer.optimize(perf_report)
                report.weights_changed = report.old_weights != report.new_weights
                from src.config import get_settings
                evo = get_settings().evolution
                if report.weights_changed:
                    if evo.auto_apply_weights:
                        self.optimizer.save_config()
                        logger.info("✅ Weights saved to fusion_weights.json")
                    else:
                        self.optimizer.save_proposed()
                        logger.info("ℹ️ Weights saved to fusion_weights.proposed.json (awaiting apply)")
            else:
                report.new_weights = dict(report.old_weights)

            # Phase 3: stock pool
            report.phase = "decide"
            from src.config import get_settings
            evo = get_settings().evolution
            try:
                if evo.auto_mutate_watchlist:
                    pool_report = self.pool_manager.evolve(db=db)
                else:
                    pool_report = self.pool_manager.analyze_pool(db)
                    if db:
                        for s in pool_report.stats:
                            if s.status == "candidate_evict":
                                db.add_evolution_suggestion(
                                    s.code, "evict", s.name,
                                    f"胜率 {s.win_rate:.1%} 低于阈值",
                                )
                            elif s.status == "candidate_add":
                                db.add_evolution_suggestion(
                                    s.code, "add", s.name, "候选加入",
                                )
                report.pool_size = pool_report.pool_size
                report.evicted = pool_report.evicted
                report.added = pool_report.added
            except Exception as e:
                logger.error("Stock pool evolution failed: %s", e)
                report.errors.append(f"股票池进化失败: {e}")

            # Phase 4: ACT (apply + report)
            report.phase = "act"
            try:
                # Weights already saved in orient phase per settings

                # D5: Agent-level evolution (track and adjust)
                try:
                    agent_suggestions = self.agent_tracker.get_suggestions()
                    logger.info("🤖 Agent evolution: %d suggestions", len(agent_suggestions))
                    report.recommendations.extend(agent_suggestions)
                except Exception as e:
                    logger.warning("Agent evolution tracking failed: %s", e)

                # Generate and save evolution report
                report.summary = self._generate_summary(report)
                report.recommendations = self._generate_recommendations(report)
                self._save_report(report)

                # Save to site data for dashboard
                self._publish_to_site(report)

                report.phase = "complete"
                logger.info("✅ Evolution cycle %s complete", report.cycle_id)

            except Exception as e:
                logger.error("Failed to apply evolution: %s", e)
                report.errors.append(f"应用进化结果失败: {e}")

        except Exception as e:
            logger.error("Evolution cycle failed: %s", e)
            report.errors.append(f"进化循环异常: {e}")
            report.phase = "error"

        return report

    # ── OODA phases ──────────────────────────────────────────────

    def _observe(self, db=None):
        """Verify yesterday's signals against actual prices."""
        if db is None:
            return None

        # Get yesterday's post-market signals
        yesterday = date.today()
        from datetime import timedelta
        # Try last 3 days (skip weekends)
        for i in range(1, 5):
            check_date = yesterday - timedelta(days=i)
            signals = db.get_latest_signals(check_date, report_type="post")
            if signals:
                signal_dicts = []
                for sig in signals:
                    meta = db.get_stock(sig.code) if db else None
                    signal_dicts.append({
                        "code": sig.code,
                        "name": meta.get("name", "") if meta else "",
                        "final_signal": sig.final_signal or "hold",
                        "final_score": sig.final_score or 0.0,
                        "hard_score": sig.hard_score or 0.0,
                        "soft_score": sig.soft_score or 0.0,
                    })
                return self.tracker.verify_signals(check_date, signal_dicts, db)

        return None

    def _generate_summary(self, report: EvolutionReport) -> str:
        """Generate a human-readable summary of the evolution cycle."""
        parts = []

        if report.signals_verified > 0:
            parts.append(
                f"验证了 {report.signals_verified} 个信号，"
                f"胜率 {report.win_rate:.1%}，"
                f"平均收益 {report.avg_return:.2f}%。"
            )

        if report.weights_changed:
            parts.append("信号权重已自动调整。")
        else:
            parts.append("权重保持稳定，无需调整。")

        if report.evicted:
            parts.append(f"从股票池剔除 {len(report.evicted)} 只表现不佳的股票。")
        if report.added:
            parts.append(f"新纳入 {len(report.added)} 只潜力股票。")

        if report.errors:
            parts.append(f"遇到 {len(report.errors)} 个问题（见详情）。")

        return " ".join(parts) if parts else "本轮进化无显著变化。"

    def _generate_recommendations(self, report: EvolutionReport) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        if report.win_rate < 0.4 and report.signals_verified > 10:
            recs.append("胜率偏低，建议审查信号融合策略，考虑增加新的数据源")

        if report.sharpe_like < -0.5:
            recs.append("夏普比率为负，风险调整后收益不佳，建议降低激进信号权重")

        if report.pool_size < 40:
            recs.append(f"股票池仅 {report.pool_size} 只，建议扩大至 45-50 只")

        if not report.weights_changed and report.signals_verified > 20:
            recs.append("权重长期未变，可考虑引入 LLM 辅助权重优化")

        if not recs:
            recs.append("系统运行良好，继续保持")

        return recs

    def _save_report(self, report: EvolutionReport):
        """Save evolution report to file."""
        report_dir = Path("output/evolution")
        report_dir.mkdir(parents=True, exist_ok=True)

        # Markdown report
        md_path = report_dir / f"{report.cycle_id}.md"
        md_path.write_text(report.to_markdown(), encoding="utf-8")

        # JSON report
        json_path = report_dir / f"{report.cycle_id}.json"
        json_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Latest symlink
        latest_path = report_dir / "latest.json"
        latest_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        logger.info("Evolution report saved to %s", md_path)

    def _publish_to_site(self, report: EvolutionReport):
        """Publish evolution data to site/data/ for dashboard display."""
        site_data = Path("site/data")
        site_data.mkdir(parents=True, exist_ok=True)

        # Save evolution summary for dashboard
        evo_data = {
            "cycle_id": report.cycle_id,
            "date": report.date,
            "win_rate": round(report.win_rate, 4),
            "avg_return": round(report.avg_return, 4),
            "sharpe_like": round(report.sharpe_like, 4),
            "signals_verified": report.signals_verified,
            "weights": {k: round(v, 3) for k, v in report.new_weights.items()},
            "pool_size": report.pool_size,
            "evicted_count": len(report.evicted),
            "added_count": len(report.added),
            "summary": report.summary,
            "status": report.phase,
        }
        path = site_data / "evolution.json"
        path.write_text(
            json.dumps(evo_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info("Evolution data published to %s", path)
