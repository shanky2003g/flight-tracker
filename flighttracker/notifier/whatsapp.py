"""Twilio WhatsApp notifier with free-form -> template fallback."""
from __future__ import annotations

import json
import logging

import requests

from ..config import TwilioConfig
from .base import Notifier, NotifyError

log = logging.getLogger(__name__)


class TwilioWhatsAppNotifier(Notifier):
    name = "whatsapp"

    def __init__(self, cfg: TwilioConfig, timeout: int = 20):
        if not cfg.configured:
            raise NotifyError("Twilio is not fully configured (SID/token/to).")
        self.cfg = cfg
        self.timeout = timeout
        self._from = self._normalize(cfg.whatsapp_from)
        self._to = self._normalize(cfg.whatsapp_to)

    @staticmethod
    def _normalize(number: str) -> str:
        return number if number.startswith("whatsapp:") else f"whatsapp:{number}"

    @property
    def _url(self) -> str:
        return (
            f"https://api.twilio.com/2010-04-01/Accounts/"
            f"{self.cfg.account_sid}/Messages.json"
        )

    def send(self, body: str, short_1: str = "", short_2: str = "") -> None:
        auth = (self.cfg.account_sid, self.cfg.auth_token)

        # 1) Free-form body (works inside the 24h session window).
        resp = requests.post(
            self._url,
            data={"From": self._from, "To": self._to, "Body": body},
            auth=auth,
            timeout=self.timeout,
        )
        if resp.status_code in (200, 201):
            log.info("WhatsApp free-form alert delivered.")
            return

        # 2) Outside the window Twilio requires an approved template (error 21654).
        if "21654" in resp.text and short_1 and short_2:
            log.info("Session window closed; falling back to Twilio template.")
            resp2 = requests.post(
                self._url,
                data={
                    "From": self._from,
                    "To": self._to,
                    "ContentSid": self.cfg.content_sid,
                    "ContentVariables": json.dumps({"1": short_1, "2": short_2}),
                },
                auth=auth,
                timeout=self.timeout,
            )
            if resp2.status_code in (200, 201):
                log.info("WhatsApp template alert delivered.")
                return
            raise NotifyError(
                f"Twilio template error {resp2.status_code}: {resp2.text[:300]}"
            )

        raise NotifyError(f"Twilio error {resp.status_code}: {resp.text[:300]}")
