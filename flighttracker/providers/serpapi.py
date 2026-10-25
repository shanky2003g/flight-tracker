"""SerpApi Google Flights provider."""
from __future__ import annotations

import logging

import requests

from ..models import Itinerary, PriceInsights, Quote, Route
from .base import FlightProvider, ProviderError

log = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search"


def _format_duration(minutes: int) -> str:
    if not minutes:
        return "N/A"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m"


def parse_quote(data: dict, route: Route) -> Quote:
    """Pure parser: turn a SerpApi response into a :class:`Quote`.

    Kept free of network I/O so it can be unit-tested with a saved fixture.
    """
    if "error" in data:
        raise ProviderError(f"SerpApi error: {data['error']}")

    all_flights = list(data.get("best_flights", [])) + list(data.get("other_flights", []))
    if not all_flights:
        raise ProviderError(f"No flights found for {route.label}.")

    cheapest = min(all_flights, key=lambda x: x.get("price") or 10**9)
    legs = cheapest.get("flights", []) or []
    layovers = cheapest.get("layovers", []) or []

    first_leg = legs[0] if legs else {}
    last_leg = legs[-1] if legs else {}

    airlines = ", ".join(
        dict.fromkeys(leg.get("airline", "Unknown") for leg in legs)
    ) or "Unknown"
    flight_numbers = " \u2192 ".join(
        leg.get("flight_number", "") for leg in legs if leg.get("flight_number")
    )

    if layovers:
        layover = ", ".join(
            f"{lo.get('name', lo.get('id', 'Hub'))} ({_format_duration(lo.get('duration', 0))})"
            for lo in layovers
        )
    else:
        layover = "Direct (Non-stop)"

    insights_raw = data.get("price_insights", {}) or {}
    typical = insights_raw.get("typical_price_range") or [0, 0]
    price = cheapest.get("price") or insights_raw.get("lowest_price")
    if price is None:
        raise ProviderError(f"No price available for {route.label}.")

    itinerary = Itinerary(
        price=int(price),
        airlines=airlines,
        flight_numbers=flight_numbers,
        departure_time=first_leg.get("departure_airport", {}).get("time", "N/A"),
        arrival_time=last_leg.get("arrival_airport", {}).get("time", "N/A"),
        duration_minutes=int(cheapest.get("total_duration", 0) or 0),
        stops=max(len(legs) - 1, 0),
        layover=layover,
    )
    insights = PriceInsights(
        level=str(insights_raw.get("price_level", "unknown")),
        typical_low=int(typical[0]) if len(typical) >= 2 and typical[0] else 0,
        typical_high=int(typical[1]) if len(typical) >= 2 and typical[1] else 0,
    )
    booking_url = data.get("search_metadata", {}).get(
        "google_flights_url", "https://www.google.com/travel/flights"
    )
    return Quote(
        route_key=route.key,
        origin=route.origin,
        destination=route.destination,
        departure_date=route.departure_date,
        currency=route.currency,
        itinerary=itinerary,
        insights=insights,
        booking_url=booking_url,
    )


class SerpApiProvider(FlightProvider):
    name = "serpapi"

    def __init__(self, api_key: str, timeout: int = 45):
        if not api_key:
            raise ProviderError("SERPAPI_KEY is required for SerpApiProvider.")
        self.api_key = api_key
        self.timeout = timeout

    def fetch(self, route: Route) -> Quote:
        params = {
            "engine": "google_flights",
            "departure_id": route.origin,
            "arrival_id": route.destination,
            "outbound_date": route.departure_date,
            "type": "2",  # one-way
            "currency": route.currency,
            "hl": "en",
            "gl": "in",
            "deep_search": "true",
            "api_key": self.api_key,
        }
        log.info("Fetching fares for %s via SerpApi", route.label)
        try:
            resp = requests.get(SERPAPI_ENDPOINT, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise ProviderError(f"SerpApi request failed: {exc}") from exc
        if resp.status_code != 200:
            raise ProviderError(f"SerpApi HTTP {resp.status_code}: {resp.text[:300]}")
        return parse_quote(resp.json(), route)
