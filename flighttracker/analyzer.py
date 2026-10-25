"""The decision algorithm.

Unlike a stateless price check, this reads the *entire* recorded history for a
route and combines several independent signals into one transparent verdict:

  * **Relative price** -- where today's fare sits in the historical distribution
    (percentile rank) and whether it ties/beats the all-time low.
  * **Trend** -- a least-squares slope over a recent window: is the fare rising
    or falling right now?
  * **Time pressure** -- days to departure; fares for thin connecting routes
    rarely fall in the final stretch, so proximity shifts us toward booking.
  * **Market context** -- Google's own ``price_level`` and typical range.

Every factor is recorded in ``Decision.reasons`` so the alert can explain *why*.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from .config import AnalyzerConfig
from .models import Decision, Observation, Quote, Route, Signal, Stats


def _median(values: List[int]) -> int:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) // 2


def _percentile_rank(prices: List[int], current: int) -> float:
    """Percentage of observations at or below ``current`` (lower = cheaper)."""
    if not prices:
        return 100.0
    at_or_below = sum(1 for p in prices if p <= current)
    return round(100.0 * at_or_below / len(prices), 1)


def _slope_per_day(obs: List[Observation]) -> float:
    """Least-squares slope of price vs. time (currency units per day)."""
    if len(obs) < 2:
        return 0.0
    t0 = obs[0].observed_at
    xs = [(o.observed_at - t0).total_seconds() / 86400.0 for o in obs]
    ys = [float(o.price) for o in obs]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    return num / denom


def _days_to_departure(departure_date: str, today: Optional[date] = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    dep = date.fromisoformat(departure_date)
    return (dep - today).days


def compute_stats(
    observations: List[Observation], current_price: int, cfg: AnalyzerConfig
) -> Stats:
    prices = [o.price for o in observations]
    prior = prices[:-1] if prices else []  # history excluding the current point

    minimum = min(prices) if prices else current_price
    is_all_time_low = bool(prior) and current_price <= min(prior) * cfg.new_low_tolerance

    # Short-term trend over the configured recent window.
    if observations:
        latest = observations[-1].observed_at
        window = [
            o
            for o in observations
            if (latest - o.observed_at).total_seconds() / 86400.0
            <= cfg.trend_window_days
        ]
    else:
        window = []
    slope = _slope_per_day(window)
    # Guard against degenerate slopes when observations are near-simultaneous
    # (too short a time base makes the least-squares slope meaningless).
    if len(window) >= 2:
        span_days = (
            window[-1].observed_at - window[0].observed_at
        ).total_seconds() / 86400.0
    else:
        span_days = 0.0
    if span_days < 0.25:
        slope = 0.0
    threshold = max(50.0, 0.005 * (_median(prices) or 1))
    if slope > threshold:
        trend_label = "rising"
    elif slope < -threshold:
        trend_label = "falling"
    else:
        trend_label = "flat"

    return Stats(
        count=len(prices),
        minimum=minimum,
        maximum=max(prices) if prices else current_price,
        median=_median(prices),
        percentile=_percentile_rank(prices, current_price),
        is_all_time_low=is_all_time_low,
        trend_per_day=round(slope, 1),
        trend_label=trend_label,
    )


def analyze(
    quote: Quote,
    observations: List[Observation],
    route: Route,
    cfg: AnalyzerConfig,
    today: Optional[date] = None,
) -> Decision:
    """Produce a :class:`Decision` from the full history for a route.

    ``observations`` must include the current quote as its last element.
    """
    current = quote.price
    stats = compute_stats(observations, current, cfg)
    prior_prices = [o.price for o in observations[:-1]]
    prior_min = min(prior_prices) if prior_prices else current
    days_left = _days_to_departure(route.departure_date, today)
    level = (quote.insights.level or "unknown").lower()

    cheap = stats.percentile <= cfg.cheap_percentile
    expensive = stats.percentile >= 70
    rising = stats.trend_label == "rising"
    falling = stats.trend_label == "falling"
    plenty_time = days_left > cfg.buy_window_days_to_departure
    target_hit = route.target_price is not None and current <= route.target_price

    reasons: List[str] = []

    # --- Cold start: not enough history to be statistical -------------------
    if stats.count < 2:
        reasons.append(
            f"Only {stats.count} data point(s) recorded so far \u2014 building history."
        )
        if level == "low":
            signal = Signal.BUY
            reasons.append("Google rates this fare as LOW vs. its typical range.")
        elif level == "high":
            signal = Signal.WAIT
            reasons.append("Google rates this fare as HIGH vs. its typical range.")
        else:
            signal = Signal.COLLECTING
        return Decision(
            signal=signal if signal != Signal.COLLECTING else Signal.COLLECTING,
            confidence="low",
            reasons=reasons,
            stats=stats,
            days_to_departure=days_left,
        )

    # --- Main decision tree -------------------------------------------------
    if days_left <= cfg.urgent_days_to_departure:
        if stats.is_all_time_low or cheap or target_hit:
            signal = Signal.STRONG_BUY
            reasons.append(
                f"Only {days_left} days to departure and the fare is in the cheap zone."
            )
        else:
            signal = Signal.URGENT
            reasons.append(
                f"Only {days_left} days left; fares on thin connecting routes rarely "
                "drop this close to departure."
            )
    elif stats.is_all_time_low or target_hit:
        signal = Signal.STRONG_BUY
        if stats.is_all_time_low:
            reasons.append(
                f"New all-time low: \u20b9{current:,} (previous best \u20b9{prior_min:,})."
            )
        if target_hit:
            reasons.append(f"At/under your target of \u20b9{route.target_price:,}.")
    elif cheap:
        signal = Signal.BUY
        reasons.append(
            f"Fare sits in the cheapest {cfg.cheap_percentile:.0f}% of everything seen "
            f"(percentile {stats.percentile:.0f})."
        )
    elif days_left <= cfg.buy_window_days_to_departure and not expensive and not falling:
        signal = Signal.BUY
        reasons.append(
            f"Inside the {cfg.buy_window_days_to_departure}-day booking window and the fare is not "
            "falling \u2014 lock it before the typical pre-departure bump."
        )
    else:
        signal = Signal.WAIT
        if expensive:
            reasons.append(
                f"Fare is pricey vs. history (percentile {stats.percentile:.0f})."
            )
        if falling:
            reasons.append("Prices are trending down \u2014 waiting may pay off.")
        if plenty_time:
            reasons.append(f"{days_left} days of runway left to catch a dip.")

    # --- Corroborating context ---------------------------------------------
    if level == "low" and signal == Signal.WAIT and not expensive:
        signal = Signal.BUY
        reasons.append("Google also rates this fare as LOW \u2014 upgraded to BUY.")

    reasons.append(
        f"Trend (last {cfg.trend_window_days}d): {stats.trend_label} "
        f"(\u20b9{stats.trend_per_day:+,.0f}/day). "
        f"Seen \u20b9{stats.minimum:,}\u2013\u20b9{stats.maximum:,}, median \u20b9{stats.median:,}."
    )
    if level in ("low", "typical", "high"):
        reasons.append(f"Google price level: {level.upper()}.")

    confidence = (
        "high"
        if stats.count >= cfg.min_observations_for_confidence
        else ("medium" if stats.count >= 3 else "low")
    )

    return Decision(
        signal=signal,
        confidence=confidence,
        reasons=reasons,
        stats=stats,
        days_to_departure=days_left,
    )
