"""Notification base — factory and interface."""

from abc import ABC, abstractmethod
from typing import Optional

from src.config import get_settings
from src.data.models import Report


class BaseNotifier(ABC):
    """Base class for all notifiers."""

    @abstractmethod
    async def send(self, report: Report) -> bool:
        """Send report. Returns True on success."""
        pass


def get_notifier() -> Optional[BaseNotifier]:
    """Factory: return configured notifier, or None if not configured."""
    settings = get_settings()
    notify_type = settings.notify.type

    if notify_type == "wecom":
        if not settings.notify.wecom_webhook:
            return None  # Webhook not configured
        from src.notify.wecom import WeComNotifier
        return WeComNotifier(settings.notify.wecom_webhook)

    elif notify_type == "email":
        if not settings.smtp_host:
            return None
        from src.notify.email import EmailNotifier
        return EmailNotifier(settings)

    return None
