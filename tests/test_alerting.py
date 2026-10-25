from datetime import datetime, timezone

from flighttracker.alerting import decide_alert
from flighttracker.config import AlertsConfig
from flighttracker.models import (
    Decision,
    Itinerary,
    PriceInsights,
    Quote,
    Signal,
    Stats,
)

CFG = AlertsConfig()  # digest window 17-23, tz Asia/Kolkata, cooldown 12h


def quote(price=9000):
    return Quote(
        route_key="KNU-IXE-2026-11-13",
        origin="KNU",
        destination="IXE",
        departure_date="2026-11-13",
        currency="INR",
        itinerary=Itinerary(price=price),
        insights=PriceInsights(),
    )


def decision(signal, all_time_low=False):
    return Decision(
        signal=signal,
        confidence="high",
        reasons=[],
        stats=Stats(count=10, is_all_time_low=all_time_low),
    )


# 12:00 UTC == 17:30 IST -> inside the evening digest window.
EVENING = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
# 06:00 UTC == 11:30 IST -> outside the window.
MORNING = datetime(2026, 10, 1, 6, 0, tzinfo=timezone.utc)


def test_digest_sent_once_per_evening():
    plan, state = decide_alert(quote(), decision(Signal.WAIT), {}, CFG, EVENING)
    assert plan.should_send and plan.kind == "digest"
    # Second evening run same day -> no duplicate digest.
    plan2, _ = decide_alert(quote(), decision(Signal.WAIT), state, CFG, EVENING)
    assert not plan2.should_send


def test_no_digest_in_morning_for_wait():
    plan, _ = decide_alert(quote(), decision(Signal.WAIT), {}, CFG, MORNING)
    assert not plan.should_send


def test_strong_buy_sent_immediately_in_morning():
    plan, state = decide_alert(quote(), decision(Signal.STRONG_BUY), {}, CFG, MORNING)
    assert plan.should_send and plan.kind == "strong_buy"
    # Within cooldown -> suppressed.
    plan2, _ = decide_alert(quote(), decision(Signal.STRONG_BUY), state, CFG, MORNING)
    assert not plan2.should_send


def test_new_low_sent_even_within_cooldown():
    d = decision(Signal.STRONG_BUY, all_time_low=True)
    plan, state = decide_alert(quote(9000), d, {}, CFG, MORNING)
    assert plan.should_send and plan.kind == "new_low"
    # A lower low later still alerts despite cooldown.
    plan2, state = decide_alert(quote(8500), d, state, CFG, MORNING)
    assert plan2.should_send and plan2.kind == "new_low"
    # Same (not lower) low does not re-alert.
    plan3, _ = decide_alert(quote(8500), d, state, CFG, MORNING)
    assert not plan3.should_send
