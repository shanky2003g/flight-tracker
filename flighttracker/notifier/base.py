"""Notifier abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod


class NotifyError(RuntimeError):
    """Raised when a notification cannot be delivered."""


class Notifier(ABC):
    name = "notifier"

    @abstractmethod
    def send(self, body: str, short_1: str = "", short_2: str = "") -> None:
        raise NotImplementedError
