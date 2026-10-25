"""Provider abstraction so fare sources are pluggable and testable."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Quote, Route


class ProviderError(RuntimeError):
    """Raised when a provider cannot return a usable quote."""


class FlightProvider(ABC):
    """Fetches a point-in-time :class:`Quote` for a route."""

    name: str = "provider"

    @abstractmethod
    def fetch(self, route: Route) -> Quote:
        raise NotImplementedError
