"""Alert dispatcher — Phase G6."""

import logging
from datetime import date

from src.data.db_manager import SignalDB
from src.notify.base import get_notifier

logger = logging.getLogger(__name__)


class AlertDispatcher:
    def __init__(self, db: SignalDB | None = None):
        self.db = db or SignalDB()

    def dispatch(self, code: str, name: str, alert_type: str, message: str,
                 severity: str = "info", notify: bool = True) -> int:
        td = date.today().isoformat()
        alert_id = self.db.save_alert(td, code, name, alert_type, message, severity)

        if notify and severity in ("watch", "action"):
            notifier = get_notifier()
            if notifier:
                try:
                    from src.data.models import Report, ReportType
                    from datetime import datetime
                    fake = Report(
                        trade_date=date.today(),
                        report_type=ReportType.PRE,
                        markdown=f"**[{severity.upper()}] {code} {name}**\n{message}",
                        generated_at=datetime.now(),
                        analyses=[],
                    )
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            asyncio.create_task(notifier.send(fake))
                        else:
                            loop.run_until_complete(notifier.send(fake))
                    except RuntimeError:
                        asyncio.run(notifier.send(fake))
                except Exception as e:
                    logger.warning("WeCom alert failed: %s", e)
        return alert_id

    def get_feed(self, trade_date: str | None = None, unread_only: bool = False,
                 severity: str | None = None) -> dict:
        td = trade_date or date.today().isoformat()
        alerts = self.db.get_alerts(td, unread_only=unread_only, severity=severity)
        return {
            "trade_date": td,
            "unread_count": self.db.count_unread_alerts(td),
            "alerts": alerts,
        }
