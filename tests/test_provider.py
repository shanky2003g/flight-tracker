import json
import os

import pytest

from flighttracker.models import Route
from flighttracker.providers.serpapi import parse_quote

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "serpapi_sample.json")


@pytest.fixture
def route():
    return Route("KNU", "IXE", "2026-11-13", "INR")


@pytest.fixture
def sample():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def test_parses_cheapest_itinerary(sample, route):
    quote = parse_quote(sample, route)
    assert quote.price == 9800  # cheapest across best + other
    assert "IndiGo" in quote.itinerary.airlines
    assert quote.itinerary.stops == 1
    assert quote.insights.level == "typical"
    assert quote.insights.typical_low == 9000
    assert quote.insights.typical_high == 14000
    assert quote.route_key == "KNU-IXE-2026-11-13"


def test_record_roundtrip(sample, route):
    quote = parse_quote(sample, route)
    rec = quote.to_record()
    assert rec["price"] == 9800
    assert rec["route_key"] == quote.route_key


def test_error_response_raises(route):
    from flighttracker.providers.base import ProviderError

    with pytest.raises(ProviderError):
        parse_quote({"error": "no flights"}, route)
