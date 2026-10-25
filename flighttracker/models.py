"""Typed data structures shared across the application."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class Route:
    """A single origin -> destination search for a fixed departure date."""

    origin: str
    destination: str
    departure_date: str  # ISO date, e.g. "2026-11-13"
    currency: str = "INR"
    target_price: Optional[int] = None

    @property
    def key(self) -> str:
        """Stable identifier used to group observations in storage."""
        return f"{self.origin}-{self.destination}-{self.departure_date}"

    @property
    def label(self) -> str:
        return f"{self.origin} \u2192 {self.destination} ({self.departure_date})"


@dataclass
class Itinerary:
    """The cheapest concrete itinerary returned by a provider."""

    price: int
    airlines: str = "Unknown"
    flight_numbers: str = ""
    departure_time: str = "N/A"
    arrival_time: str = "N/A"
    duration_minutes: int = 0
    stops: int = 0
    layover: str = "Direct (Non-stop)"


@dataclass
class PriceInsights:
    """Market context Google exposes alongside fares (optional)."""

    level: str = "unknown"  # low | typical | high | unknown
    typical_low: int = 0
    typical_high: int = 0


@dataclass
class Quote:
    """A single point-in-time measurement for a route."""

    route_key: str
    origin: str
    destination: str
    departure_date: str
    currency: str
    itinerary: Itinerary
    insights: PriceInsights
    booking_url: str = ""
    observed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def price(self) -> int:
        return self.itinerary.price

    def to_record(self) -> dict:
        """Flatten to a JSON-serializable history record."""
        return {
            "observed_at": self.observed_at,
            "route_key": self.route_key,
            "origin": self.origin,
            "destination": self.destination,
            "departure_date": self.departure_date,
            "currency": self.currency,
            "price": self.itinerary.price,
            "price_level": self.insights.level,
            "typical_low": self.insights.typical_low,
            "typical_high": self.insights.typical_high,
            "airlines": self.itinerary.airlines,
            "flight_numbers": self.itinerary.flight_numbers,
            "departure_time": self.itinerary.departure_time,
            "arrival_time": self.itinerary.arrival_time,
            "duration_minutes": self.itinerary.duration_minutes,
            "stops": self.itinerary.stops,
            "layover": self.itinerary.layover,
            "booking_url": self.booking_url,
        }


@dataclass
class Observation:
    """A historical record loaded back from storage."""

    observed_at: datetime
    price: int
    price_level: str = "unknown"

    @classmethod
    def from_record(cls, rec: dict) -> "Observation":
        ts = rec["observed_at"]
        dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return cls(
            observed_at=dt,
            price=int(rec["price"]),
            price_level=str(rec.get("price_level", "unknown")),
        )


class Signal(str, Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    URGENT = "URGENT"
    WAIT = "WAIT"
    COLLECTING = "COLLECTING"

    @property
    def emoji(self) -> str:
        return {
            Signal.STRONG_BUY: "\U0001F7E2",
            Signal.BUY: "\U0001F7E2",
            Signal.URGENT: "\U0001F534",
            Signal.WAIT: "\u23F3",
            Signal.COLLECTING: "\U0001F4CA",
        }[self]

    @property
    def headline(self) -> str:
        return {
            Signal.STRONG_BUY: "STRONG BUY \u2014 book now",
            Signal.BUY: "BUY \u2014 good time to book",
            Signal.URGENT: "URGENT \u2014 departure is near",
            Signal.WAIT: "WAIT \u2014 hold and watch",
            Signal.COLLECTING: "COLLECTING DATA \u2014 provisional read",
        }[self]


@dataclass
class Stats:
    count: int = 0
    minimum: int = 0
    maximum: int = 0
    median: int = 0
    percentile: float = 100.0  # current price's percentile rank in history
    is_all_time_low: bool = False
    trend_per_day: float = 0.0  # +ve = rising, -ve = falling (currency/day)
    trend_label: str = "flat"


@dataclass
class Decision:
    signal: Signal
    confidence: str  # low | medium | high
    reasons: list = field(default_factory=list)
    stats: Stats = field(default_factory=Stats)
    days_to_departure: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signal"] = self.signal.value
        return d
