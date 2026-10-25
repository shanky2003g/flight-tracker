"""Console notifier -- used for dry runs and local testing."""
from __future__ import annotations

from .base import Notifier


class ConsoleNotifier(Notifier):
    name = "console"

    def send(self, body: str, short_1: str = "", short_2: str = "") -> None:
        print("\n===== ALERT (console) =====")
        print(body)
        print("===========================\n")
