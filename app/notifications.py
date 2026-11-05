import logging

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, settings: Settings):
        self.url = (
            settings.discord_webhook_url.get_secret_value()
            if settings.discord_webhook_url
            else None
        )

    def send(self, title: str, message: str, *, urgent: bool = False) -> None:
        if not self.url:
            return
        color = 0xB42318 if urgent else 0x175CD3
        try:
            httpx.post(
                self.url,
                json={
                    "username": "A1 Paper Bot",
                    "embeds": [{"title": title, "description": message, "color": color}],
                },
                timeout=5,
            ).raise_for_status()
        except Exception:
            logger.exception("Discord notification failed")
