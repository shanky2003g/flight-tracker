"""Orchestration: fetch -> record -> analyze -> decide -> notify, per route."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .alerting import decide_alert
from .analyzer import analyze
from .config import Config
from .messages import format_message, short_summaries
from .models import Decision, Quote, Route
from .notifier.base import Notifier, NotifyError
from .providers.base import FlightProvider, ProviderError
from .storage import HistoryStore, StateStore

log = logging.getLogger(__name__)


@dataclass
class RouteResult:
    route: Route
    quote: Optional[Quote] = None
    decision: Optional[Decision] = None
    alerted: bool = False
    alert_kind: str = ""
    error: str = ""


class Pipeline:
    def __init__(
        self,
        config: Config,
        provider: FlightProvider,
        notifier: Optional[Notifier] = None,
        *,
        dry_run: bool = False,
    ):
        self.config = config
        self.provider = provider
        self.notifier = notifier
        self.dry_run = dry_run
        self.history = HistoryStore(config.storage.history_path)
        self.state = StateStore(config.storage.state_path)

    def run(self, now_utc: Optional[datetime] = None) -> List[RouteResult]:
        now_utc = now_utc or datetime.now(timezone.utc)
        results: List[RouteResult] = []
        for route in self.config.routes:
            results.append(self._run_route(route, now_utc))
        self.state.save()
        return results

    def _run_route(self, route: Route, now_utc: datetime) -> RouteResult:
        result = RouteResult(route=route)
        try:
            quote = self.provider.fetch(route)
        except ProviderError as exc:
            log.error("Fetch failed for %s: %s", route.label, exc)
            result.error = str(exc)
            return result

        result.quote = quote
        if not self.dry_run:
            self.history.append(quote)

        observations = self.history.observations(route.key)
        if self.dry_run and (not observations or observations[-1].price != quote.price):
            # In dry-run we did not persist; include the current quote virtually.
            from .models import Observation

            observations = observations + [
                Observation.from_record(quote.to_record())
            ]

        decision = analyze(quote, observations, route, self.config.analyzer, now_utc.date())
        result.decision = decision

        message = format_message(quote, decision, route)
        log.info("\n%s", message)

        plan, new_state = decide_alert(
            quote, decision, self.state.get(route.key), self.config.alerts, now_utc
        )
        self.state.set(route.key, new_state)

        if plan.should_send:
            body = format_message(quote, decision, route, reason=plan.reason)
            s1, s2 = short_summaries(quote, decision, route)
            self._notify(body, s1, s2)
            result.alerted = True
            result.alert_kind = plan.kind
        else:
            log.info("No alert sent for %s (conditions not met).", route.label)
        return result

    def _notify(self, body: str, s1: str, s2: str) -> None:
        if self.notifier is None or self.dry_run:
            log.info("[dry-run] Would send alert:\n%s", body)
            print(body)
            return
        try:
            self.notifier.send(body, s1, s2)
        except NotifyError as exc:
            log.error("Alert delivery failed: %s", exc)
