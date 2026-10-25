"""Decide *whether* and *why* to actually push an alert.

Two independent triggers, as requested:
  * a once-a-day evening **digest** with the current price and verdict, and
  * immediate **strong-buy / new-all-time-low** alerts (deduped via a cooldown),
    so a sudden great fare is never missed but nothing spams.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

try:  # stdlib since Python 3.9
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .config import AlertsConfig
from .models import Decision, Quote, Signal


@dataclass
class AlertPlan:
    should_send: bool
    kind: str = ""  # digest | strong_buy | new_low | urgent
    reason: str = ""


PRIORITY_SIGNALS = {Signal.STRONG_BUY, Signal.URGENT}


def _now_local(cfg: AlertsConfig, now_utc: Optional[datetime] = None) -> datetime:
    now_utc = now_utc or datetime.now(timezone.utc)
    if ZoneInfo is not None:
        try:
            return now_utc.astimezone(ZoneInfo(cfg.timezone))
        except Exception:
            pass
    return now_utc


def decide_alert(
    quote: Quote,
    decision: Decision,
    state: dict,
    cfg: AlertsConfig,
    now_utc: Optional[datetime] = None,
) -> Tuple[AlertPlan, dict]:
    """Return an :class:`AlertPlan` plus the updated per-route state to persist."""
    now_utc = now_utc or datetime.now(timezone.utc)
    local = _now_local(cfg, now_utc)
    today = local.date().isoformat()
    state = dict(state)  # copy; caller persists

    # ---- Immediate triggers ------------------------------------------------
    new_low = decision.stats.is_all_time_low
    last_low = state.get("last_alerted_low")
    is_fresh_low = new_low and (last_low is None or quote.price < last_low)

    last_priority = state.get("last_priority_at")
    cooldown_ok = True
    if last_priority:
        try:
            last_dt = datetime.fromisoformat(last_priority)
            cooldown_ok = now_utc - last_dt >= timedelta(
                hours=cfg.strong_buy_cooldown_hours
            )
        except ValueError:
            cooldown_ok = True
    priority = decision.signal in PRIORITY_SIGNALS and cooldown_ok

    # ---- Daily evening digest ---------------------------------------------
    in_evening = cfg.digest_hour_start <= local.hour < cfg.digest_hour_end
    digest_due = in_evening and state.get("last_digest_date") != today

    plan = AlertPlan(should_send=False)

    if is_fresh_low:
        plan = AlertPlan(True, "new_low", "New all-time low fare")
    elif priority and decision.signal == Signal.STRONG_BUY:
        plan = AlertPlan(True, "strong_buy", "Strong-buy signal")
    elif priority and decision.signal == Signal.URGENT:
        plan = AlertPlan(True, "urgent", "Departure is near")
    elif digest_due:
        plan = AlertPlan(True, "digest", "Daily evening update")

    # ---- Record what we sent so we don't repeat it ------------------------
    if plan.should_send:
        if plan.kind in ("strong_buy", "urgent", "new_low"):
            state["last_priority_at"] = now_utc.isoformat()
        if plan.kind == "new_low":
            state["last_alerted_low"] = quote.price
        if digest_due:
            # A digest covers the day even if we led with a priority alert.
            state["last_digest_date"] = today
        if plan.kind == "digest":
            state["last_digest_date"] = today

    state["last_seen_price"] = quote.price
    state["last_run_at"] = now_utc.isoformat()
    return plan, state
