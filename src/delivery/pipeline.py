"""Unified delivery: analyze → site → publish."""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from src.config import get_settings
from src.data.models import Report, ReportType

logger = logging.getLogger(__name__)


class DeliveryPipeline:
    """Shared full/fast delivery for CLI, scheduler, and API."""

    async def run_full(
        self,
        report_type: ReportType,
        symbols: list[str] | None = None,
        publish: bool = False,
        job_id: str | None = None,
    ) -> Report:
        from src.orchestrator.pipeline import run_analysis
        from src.site.generator import generate_site
        from src.export.static_exporter import StaticExporter
        from src.data.db_manager import SignalDB

        db = SignalDB()
        if job_id:
            db.update_job(job_id, "running", 0.1, "分析中")

        try:
            report = await run_analysis(report_type, symbols, persist=True)
            if job_id:
                db.update_job(job_id, "running", 0.6, "生成站点", len(report.analyses))

            generate_site(report)
            StaticExporter().export_from_report(report)

            if publish:
                if job_id:
                    db.update_job(job_id, "running", 0.85, "发布 GitHub")
                ok = self.publish_github(report)
                if ok:
                    db.record_publish(
                        report.report_type.value,
                        len(report.analyses),
                        source="full",
                    )

            if job_id:
                db.update_job(
                    job_id, "completed", 1.0, "完成",
                    symbol_count=len(report.analyses),
                )
            return report
        except Exception as e:
            if job_id:
                db.update_job(job_id, "failed", 0, str(e))
            raise

    async def run_fast(self, job_id: str | None = None) -> dict:
        from src.orchestrator.pipeline import run_fast_analysis
        from src.data.db_manager import SignalDB

        db = SignalDB()
        if job_id:
            db.update_job(job_id, "running", 0.2, "盘中 Fast 更新")
        try:
            result = await run_fast_analysis()
            if job_id:
                db.update_job(job_id, "completed", 1.0, "Fast 完成", result.get("count", 0))
            return result
        except Exception as e:
            if job_id:
                db.update_job(job_id, "failed", 0, str(e))
            raise

    def publish_github(self, report: Report | None = None) -> bool:
        from src.publish.github import publish_to_github

        if report is not None:
            return publish_to_github(report)
        # docs-only publish after export
        from src.publish.github import publish_docs_only
        return publish_docs_only()

    @staticmethod
    def new_job_id() -> str:
        return str(uuid.uuid4())[:8]
