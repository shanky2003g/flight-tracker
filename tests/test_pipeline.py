from datetime import datetime, timezone

from flighttracker.config import (
    AlertsConfig,
    AnalyzerConfig,
    Config,
    StorageConfig,
)
from flighttracker.models import Itinerary, PriceInsights, Quote, Route
from flighttracker.notifier.base import Notifier
from flighttracker.pipeline import Pipeline
from flighttracker.providers.base import FlightProvider


class FakeProvider(FlightProvider):
    def __init__(self, price):
        self.price = price

    def fetch(self, route):
        return Quote(
            route_key=route.key,
            origin=route.origin,
            destination=route.destination,
            departure_date=route.departure_date,
            currency=route.currency,
            itinerary=Itinerary(price=self.price, airlines="IndiGo"),
            insights=PriceInsights(level="typical", typical_low=9000, typical_high=14000),
        )


class RecordingNotifier(Notifier):
    def __init__(self):
        self.sent = []

    def send(self, body, short_1="", short_2=""):
        self.sent.append(body)


def make_config(tmp_path):
    return Config(
        routes=[Route("KNU", "IXE", "2026-11-13", "INR")],
        analyzer=AnalyzerConfig(),
        alerts=AlertsConfig(),
        storage=StorageConfig(
            history_path=str(tmp_path / "history.jsonl"),
            state_path=str(tmp_path / "state.json"),
        ),
    )


def test_pipeline_records_and_alerts(tmp_path):
    cfg = make_config(tmp_path)
    notifier = RecordingNotifier()
    evening = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)  # 17:30 IST

    pipe = Pipeline(cfg, FakeProvider(9800), notifier)
    results = pipe.run(now_utc=evening)

    assert len(results) == 1
    assert results[0].quote.price == 9800
    assert (tmp_path / "history.jsonl").exists()
    # Evening -> a digest alert goes out.
    assert len(notifier.sent) == 1


def test_pipeline_builds_history_across_runs(tmp_path):
    cfg = make_config(tmp_path)
    morning = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)

    Pipeline(cfg, FakeProvider(12000), RecordingNotifier()).run(now_utc=morning)
    Pipeline(cfg, FakeProvider(11000), RecordingNotifier()).run(now_utc=morning)
    r = Pipeline(cfg, FakeProvider(8000), RecordingNotifier()).run(now_utc=morning)

    # Third run sees a falling history and a brand-new all-time low.
    assert r[0].decision.stats.count == 3
    assert r[0].decision.stats.is_all_time_low
    assert r[0].alerted and r[0].alert_kind == "new_low"


def test_dry_run_does_not_persist(tmp_path):
    cfg = make_config(tmp_path)
    pipe = Pipeline(cfg, FakeProvider(9800), RecordingNotifier(), dry_run=True)
    pipe.run(now_utc=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc))
    assert not (tmp_path / "history.jsonl").exists()
