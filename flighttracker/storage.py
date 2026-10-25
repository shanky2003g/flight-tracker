"""Durable, git-friendly storage: append-only JSONL history + JSON state.

GitHub Actions runners are ephemeral, so history is persisted as a plain-text
JSONL file that the workflow commits back to the repository after each run.
"""
from __future__ import annotations

import json
import logging
import os
from typing import List

from .models import Observation, Quote

log = logging.getLogger(__name__)


class HistoryStore:
    """Append-only price history, one JSON object per line."""

    def __init__(self, path: str):
        self.path = path

    def append(self, quote: Quote) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(quote.to_record(), ensure_ascii=False) + "\n")
        log.info("Recorded %s @ %s%s", quote.route_key, quote.currency, quote.price)

    def observations(self, route_key: str) -> List[Observation]:
        """Return observations for a route, sorted oldest -> newest."""
        if not os.path.exists(self.path):
            return []
        out: List[Observation] = []
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Skipping malformed history line")
                    continue
                if rec.get("route_key") == route_key:
                    out.append(Observation.from_record(rec))
        out.sort(key=lambda o: o.observed_at)
        return out


class StateStore:
    """Small JSON blob tracking alert bookkeeping across runs."""

    def __init__(self, path: str):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return json.load(fh) or {}
        except (json.JSONDecodeError, OSError):
            log.warning("Resetting unreadable state file %s", self.path)
            return {}

    def get(self, route_key: str) -> dict:
        return self._data.get(route_key, {})

    def set(self, route_key: str, value: dict) -> None:
        self._data[route_key] = value

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)
