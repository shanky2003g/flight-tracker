"""Telegram Bot notifier.

Far simpler than WhatsApp/Twilio for personal alerts: no 24h session window,
no template approval. You just need a bot token (from @BotFather) and your
chat id. Messages send anytime.
"""
from __future__ import annotations

import logging

import requests

from ..config import TelegramConfig
from .base import Notifier, NotifyError

log = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    name = "telegram"

    def __init__(self, cfg: TelegramConfig, timeout: int = 20):
        if not cfg.configured:
            raise NotifyError("Telegram is not configured (bot token / chat id).")
        self.cfg = cfg
        self.timeout = timeout

    @property
    def _url(self) -> str:
        return f"https://api.telegram.org/bot{self.cfg.bot_token}/sendMessage"

    def _post(self, text: str, parse_mode: str = "") -> requests.Response:
        payload = {
            "chat_id": self.cfg.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return requests.post(self._url, data=payload, timeout=self.timeout)

    def send(self, body: str, short_1: str = "", short_2: str = "") -> None:
        # Try Markdown first; if Telegram can't parse the entities, resend as
        # plain text so an alert is never lost to a formatting error.
        resp = self._post(body, parse_mode="Markdown")
        if resp.status_code == 200:
            log.info("Telegram alert delivered.")
            return
        if resp.status_code == 400:
            log.warning("Telegram rejected Markdown; retrying as plain text.")
            resp = self._post(body)
            if resp.status_code == 200:
                log.info("Telegram alert delivered (plain text).")
                return
        raise NotifyError(f"Telegram error {resp.status_code}: {resp.text[:300]}")
