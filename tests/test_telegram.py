"""Tests for the Telegram notifier."""
import pytest

from flighttracker.config import TelegramConfig
from flighttracker.notifier.base import NotifyError
from flighttracker.notifier.telegram import TelegramNotifier


class FakeResp:
    def __init__(self, status_code, text="ok"):
        self.status_code = status_code
        self.text = text


def test_requires_config():
    with pytest.raises(NotifyError):
        TelegramNotifier(TelegramConfig())


def test_send_success(monkeypatch):
    calls = []

    def fake_post(url, data, timeout):
        calls.append((url, data))
        return FakeResp(200)

    monkeypatch.setattr("flighttracker.notifier.telegram.requests.post", fake_post)
    n = TelegramNotifier(TelegramConfig(bot_token="abc", chat_id="123"))
    n.send("*hi*")
    assert len(calls) == 1
    assert "botabc/sendMessage" in calls[0][0]
    assert calls[0][1]["chat_id"] == "123"
    assert calls[0][1]["parse_mode"] == "Markdown"


def test_send_falls_back_to_plain_on_400(monkeypatch):
    responses = [FakeResp(400, "bad entities"), FakeResp(200)]
    seen = []

    def fake_post(url, data, timeout):
        seen.append(data)
        return responses[len(seen) - 1]

    monkeypatch.setattr("flighttracker.notifier.telegram.requests.post", fake_post)
    n = TelegramNotifier(TelegramConfig(bot_token="abc", chat_id="123"))
    n.send("*hi*")
    assert len(seen) == 2
    assert "parse_mode" in seen[0]
    assert "parse_mode" not in seen[1]


def test_send_raises_on_error(monkeypatch):
    monkeypatch.setattr(
        "flighttracker.notifier.telegram.requests.post",
        lambda url, data, timeout: FakeResp(403, "forbidden"),
    )
    n = TelegramNotifier(TelegramConfig(bot_token="abc", chat_id="123"))
    with pytest.raises(NotifyError):
        n.send("hi")
