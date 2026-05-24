"""WeCom webhook notifier."""

import logging
from typing import Optional

import httpx

from src.data.models import Report
from src.notify.base import BaseNotifier

logger = logging.getLogger(__name__)


class WeComNotifier(BaseNotifier):
    """Send Markdown report via WeCom group webhook."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, report: Report) -> bool:
        """Send report markdown to WeCom group.

        WeCom supports max 4096 chars for markdown, so we truncate.
        """
        # Truncate to fit WeCom limit
        content = report.markdown[:4000]
        if len(report.markdown) > 4000:
            content += "\n\n...(完整报告请查看 GitHub Pages)"

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode") == 0:
                    logger.info("WeCom notification sent successfully")
                    return True
                else:
                    logger.error("WeCom API error: %s", data)
                    return False
        except Exception as e:
            logger.error("WeCom send failed: %s", e)
            return False
