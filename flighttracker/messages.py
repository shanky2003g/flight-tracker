"""Human-readable message formatting for alerts."""
from __future__ import annotations

from .models import Decision, Quote, Route


def _money(cur: str, amount: int) -> str:
    symbol = "\u20b9" if cur == "INR" else ""
    return f"{symbol}{amount:,}" if symbol else f"{amount:,} {cur}"


def format_message(quote: Quote, decision: Decision, route: Route, reason: str = "") -> str:
    """The full, rich WhatsApp/console message."""
    it = quote.itinerary
    ins = quote.insights
    cur = quote.currency
    sig = decision.signal
    st = decision.stats

    typical = (
        f"{_money(cur, ins.typical_low)} \u2013 {_money(cur, ins.typical_high)}"
        if ins.typical_low and ins.typical_high
        else "N/A"
    )
    if st.count >= 2:
        history_line = (
            f"*History:* low {_money(cur, st.minimum)} / median "
            f"{_money(cur, st.median)} / high {_money(cur, st.maximum)} "
            f"({st.count} checks)\n"
            f"*Today vs history:* {st.percentile:.0f}th percentile, trend {st.trend_label}\n"
        )
    else:
        history_line = f"*History:* building up ({st.count} check so far)\n"

    reasons = "\n".join(f"\u2022 {r}" for r in decision.reasons)

    header = f"{sig.emoji} *{route.origin} \u2192 {route.destination} ({route.departure_date})*"
    if reason:
        header += f"\n_{reason}_"

    return (
        f"{header}\n"
        f"\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\n"
        f"*Verdict:* {sig.emoji} {sig.headline} ({decision.confidence} confidence)\n"
        f"*Current fare:* {_money(cur, quote.price)}\n"
        f"*Google rating:* {ins.level.upper()} (typical {typical})\n"
        f"*Days to departure:* {decision.days_to_departure}\n"
        f"{history_line}\n"
        f"\U0001F6EB *Cheapest itinerary:*\n"
        f"\u2022 {it.airlines} {('(' + it.flight_numbers + ')') if it.flight_numbers else ''}\n"
        f"\u2022 Depart {it.departure_time} \u2192 Arrive {it.arrival_time}\n"
        f"\u2022 {it.layover} \u00b7 {it.duration_minutes // 60}h {it.duration_minutes % 60}m\n\n"
        f"\U0001F4A1 *Why:*\n{reasons}\n\n"
        f"\U0001F517 {quote.booking_url}"
    )


def short_summaries(quote: Quote, decision: Decision, route: Route) -> tuple:
    """Two short strings for Twilio template fallback (ContentVariables 1 & 2)."""
    one = f"{route.origin}->{route.destination} {route.departure_date} | {decision.signal.headline}"
    two = f"{_money(quote.currency, quote.price)} | {quote.itinerary.airlines} ({quote.itinerary.departure_time})"
    return one, two
