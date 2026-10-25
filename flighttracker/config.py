"""Configuration loading: non-secret settings from YAML, secrets from env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml

from .models import Route


@dataclass
class AnalyzerConfig:
    new_low_tolerance: float = 1.00
    cheap_percentile: float = 25.0
    trend_window_days: int = 7
    min_observations_for_confidence: int = 6
    urgent_days_to_departure: int = 10
    buy_window_days_to_departure: int = 16


@dataclass
class AlertsConfig:
    digest_hour_start: int = 17
    digest_hour_end: int = 23
    strong_buy_cooldown_hours: int = 12
    timezone: str = "Asia/Kolkata"


@dataclass
class StorageConfig:
    history_path: str = "data/price_history.jsonl"
    state_path: str = "data/alert_state.json"


@dataclass
class TwilioConfig:
    account_sid: str = ""
    auth_token: str = ""
    whatsapp_from: str = "whatsapp:+14155238886"
    whatsapp_to: str = ""
    content_sid: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.whatsapp_to)


@dataclass
class Config:
    routes: List[Route] = field(default_factory=list)
    analyzer: AnalyzerConfig = field(default_factory=AnalyzerConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    twilio: TwilioConfig = field(default_factory=TwilioConfig)
    serpapi_key: str = ""


def _route_from_dict(d: dict) -> Route:
    dep = d["departure_date"]
    # YAML may parse a bare date into a datetime.date; normalize to ISO string.
    dep = dep.isoformat() if hasattr(dep, "isoformat") else str(dep)
    target = d.get("target_price")
    return Route(
        origin=str(d["origin"]).upper(),
        destination=str(d["destination"]).upper(),
        departure_date=dep,
        currency=str(d.get("currency", "INR")).upper(),
        target_price=int(target) if target not in (None, "") else None,
    )


def load_config(path: str = "config.yaml") -> Config:
    """Load YAML settings and overlay secrets from the environment."""
    raw: dict = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    routes = [_route_from_dict(r) for r in raw.get("routes", [])]

    cfg = Config(
        routes=routes,
        analyzer=AnalyzerConfig(**(raw.get("analyzer") or {})),
        alerts=AlertsConfig(**(raw.get("alerts") or {})),
        storage=StorageConfig(**(raw.get("storage") or {})),
    )

    cfg.serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    cfg.twilio = TwilioConfig(
        account_sid=os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
        auth_token=os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
        whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip(),
        whatsapp_to=os.getenv("WHATSAPP_TO", "").strip(),
        content_sid=os.getenv(
            "TWILIO_CONTENT_SID", ""
        ).strip(),
    )
    return cfg
