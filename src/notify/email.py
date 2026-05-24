"""Email notifier via SMTP."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import Settings
from src.data.models import Report
from src.notify.base import BaseNotifier

logger = logging.getLogger(__name__)


class EmailNotifier(BaseNotifier):
    """Send report via SMTP email."""

    def __init__(self, settings: Settings):
        self.smtp_host = settings.smtp_host
        self.smtp_port = settings.smtp_port
        self.smtp_user = settings.smtp_user
        self.smtp_password = settings.smtp_password
        self.smtp_to = settings.smtp_to

    async def send(self, report: Report) -> bool:
        """Send report as HTML email."""
        type_label = "盘前" if report.report_type.value == "pre" else "盘后"
        subject = f"Stock Copilot {report.trade_date} {type_label} 分析报告"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_user
        msg["To"] = self.smtp_to

        # Convert markdown to plain text body
        text_body = report.markdown.replace("#", "").replace("##", "").replace("###", "")
        text_body = text_body.replace("**", "").replace("|", "").replace("---", "")

        html_body = f"""
        <html>
        <body style="font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px;">
            <pre style="white-space: pre-wrap; font-size: 14px; line-height: 1.6;">
{text_body}
            </pre>
        </body>
        </html>
        """

        msg.attach(MIMEText(text_body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, self.smtp_to, msg.as_string())
            logger.info("Email sent to %s", self.smtp_to)
            return True
        except Exception as e:
            logger.error("Email send failed: %s", e)
            return False
