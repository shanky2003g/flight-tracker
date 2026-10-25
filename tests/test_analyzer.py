from datetime import date, datetime, timedelta, timezone

from flighttracker.analyzer import analyze, compute_stats
from flighttracker.config import AnalyzerConfig
from flighttracker.models import (
    Itinerary,
    Observation,
    PriceInsights,
    Quote,
    Route,
)

CFG = AnalyzerConfig()
ROUTE = Route("KNU", "IXE", "2026-11-13", "INR")
TODAY = date(2026, 10, 1)  # ~43 days out -> plenty of runway


def obs(prices, start_days_ago=None):
    """Build observations spaced one day apart, oldest first."""
    n = len(prices)
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [
        Observation(observed_at=base + timedelta(days=i), price=p)
        for i, p in enumerate(prices)
    ]


def quote(price, level="typical", low=9000, high=14000):
    return Quote(
        route_key=ROUTE.key,
        origin="KNU",
        destination="IXE",
        departure_date="2026-11-13",
        currency="INR",
        itinerary=Itinerary(price=price),
        insights=PriceInsights(level=level, typical_low=low, typical_high=high),
    )


def test_cold_start_uses_google_level():
    history = obs([9800])
    d = analyze(quote(9800, level="low"), history, ROUTE, CFG, TODAY)
    assert d.confidence == "low"
    assert d.signal.value in ("BUY", "COLLECTING")


def test_all_time_low_is_strong_buy():
    prices = [12000, 11500, 11000, 10500, 10000, 8000]
    d = analyze(quote(8000), obs(prices), ROUTE, CFG, TODAY)
    assert d.signal.value == "STRONG_BUY"
    assert d.stats.is_all_time_low


def test_expensive_with_runway_waits():
    prices = [9000, 9500, 10000, 10500, 11000, 13000]
    d = analyze(quote(13000), obs(prices), ROUTE, CFG, TODAY)
    assert d.signal.value == "WAIT"
    assert d.stats.percentile >= 70


def test_cheap_percentile_is_buy():
    # 9200 is the 2nd-lowest of 10 (20th percentile) -> cheap but not a new low.
    prices = [9000, 9500, 10000, 10500, 11000, 11500, 12000, 12500, 13000, 9200]
    d = analyze(quote(9200), obs(prices), ROUTE, CFG, TODAY)
    assert d.signal.value in ("BUY", "STRONG_BUY")


def test_urgent_when_departure_near_and_not_cheap():
    prices = [9000, 9500, 10000, 10500, 11000, 12000]
    near = date(2026, 11, 8)  # 5 days before departure
    d = analyze(quote(12000), obs(prices), ROUTE, CFG, near)
    assert d.signal.value in ("URGENT", "STRONG_BUY")
    assert d.days_to_departure == 5


def test_stats_trend_detection():
    rising = obs([9000, 9500, 10000, 10500, 11000, 11500])
    st = compute_stats(rising, 11500, CFG)
    assert st.trend_label == "rising"
    falling = obs([12000, 11500, 11000, 10500, 10000, 9500])
    st2 = compute_stats(falling, 9500, CFG)
    assert st2.trend_label == "falling"


def test_target_price_overrides_to_strong_buy():
    route = Route("KNU", "IXE", "2026-11-13", "INR", target_price=9500)
    prices = [12000, 11000, 10500, 10000, 9800, 9400]
    d = analyze(quote(9400), obs(prices), route, CFG, TODAY)
    assert d.signal.value == "STRONG_BUY"
