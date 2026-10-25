import os
import sys
import requests
from datetime import date

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip()
WHATSAPP_TO = os.getenv("WHATSAPP_TO", "").strip()

ORIGIN = "KNU"
DESTINATION = "IXE"
DEPARTURE_DATE = "2026-11-13"
TARGET_PRICE = 9200

CLEARTRIP_URL = (
    "https://www.cleartrip.com/flights/results?adults=1&childs=0&infants=0"
    "&class=Economy&depart_date=13%2F11%2F2026&from=KNU&to=IXE&rnd_one=O"
)

def validate_config():
    missing = [k for k, v in [
        ("SERPAPI_KEY", SERPAPI_KEY),
        ("TWILIO_ACCOUNT_SID", TWILIO_ACCOUNT_SID),
        ("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN),
        ("WHATSAPP_TO", WHATSAPP_TO),
    ] if not v]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    global TWILIO_WHATSAPP_FROM, WHATSAPP_TO
    if not TWILIO_WHATSAPP_FROM.startswith("whatsapp:"):
        TWILIO_WHATSAPP_FROM = f"whatsapp:{TWILIO_WHATSAPP_FROM}"
    if not WHATSAPP_TO.startswith("whatsapp:"):
        WHATSAPP_TO = f"whatsapp:{WHATSAPP_TO}"

def format_duration(minutes: int) -> str:
    if not minutes:
        return "N/A"
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m}m"

def fetch_flight_data() -> dict:
    params = {
        "engine": "google_flights",
        "departure_id": ORIGIN,
        "arrival_id": DESTINATION,
        "outbound_date": DEPARTURE_DATE,
        "type": "2",
        "currency": "INR",
        "hl": "en",
        "gl": "in",
        "deep_search": "true",
        "api_key": SERPAPI_KEY,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=45)
    if resp.status_code != 200:
        raise RuntimeError(f"SerpApi HTTP {resp.status_code}: {resp.text}")
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"SerpApi Error: {data['error']}")
    return data

def parse_best_itinerary(data: dict) -> dict:
    all_flights = data.get("best_flights", []) + data.get("other_flights", [])
    if not all_flights:
        raise RuntimeError("No flights found for KNU -> IXE on 2026-11-13.")

    cheapest = min(all_flights, key=lambda x: x.get("price", 999999))
    legs = cheapest.get("flights", [])
    layovers = cheapest.get("layovers", [])

    first_leg = legs[0] if legs else {}
    last_leg = legs[-1] if legs else {}

    dep_time = first_leg.get("departure_airport", {}).get("time", "N/A")
    arr_time = last_leg.get("arrival_airport", {}).get("time", "N/A")
    airlines = ", ".join(dict.fromkeys(leg.get("airline", "Unknown") for leg in legs))
    flight_nums = " -> ".join(leg.get("flight_number", "") for leg in legs if leg.get("flight_number"))

    if layovers:
        layover_str = ", ".join(
            f"{l.get('name', l.get('id', 'Hub'))} ({format_duration(l.get('duration', 0))})"
            for l in layovers
        )
    else:
        layover_str = "Direct (Non-stop)"

    insights = data.get("price_insights", {})
    lowest_price = cheapest.get("price") or insights.get("lowest_price")
    price_level = insights.get("price_level", "unknown")
    typical_range = insights.get("typical_price_range", [0, 0])

    return {
        "price": int(lowest_price),
        "price_level": price_level,
        "typical_low": typical_range[0] if len(typical_range) >= 2 else 0,
        "typical_high": typical_range[1] if len(typical_range) >= 2 else 0,
        "airlines": airlines,
        "flight_nums": flight_nums,
        "dep_time": dep_time,
        "arr_time": arr_time,
        "total_duration": format_duration(cheapest.get("total_duration", 0)),
        "layover": layover_str,
    }

def evaluate_decision(info: dict, days_left: int) -> tuple[str, str]:
    price = info["price"]
    level = info["price_level"].lower()
    t_low, t_high = info["typical_low"], info["typical_high"]
    range_str = f"₹{t_low:,}–₹{t_high:,}" if t_low and t_high else "N/A"

    if price <= TARGET_PRICE or level == "low":
        return (
            "🟢 STRONG BUY (BOOK NOW)",
            f"Fare (₹{price:,}) is in the lowest bucket (Typical: {range_str}). Lock it in before the bucket sells out!",
        )
    if 10 <= days_left <= 14 and level != "high":
        return (
            "🟡 BUY WINDOW (14-DAY CLIFF)",
            f"{days_left} days left. Domestic airline algorithms bump fare buckets inside 14 days. Book today if ₹{price:,} fits your budget.",
        )
    if days_left < 10:
        return (
            "🔴 URGENT (FINAL 10 DAYS)",
            f"Only {days_left} days left! Connecting routes from Kanpur (KNU) rarely drop in the final week due to tight seat inventory.",
        )
    return (
        "⏳ WAIT & WATCH",
        f"{days_left} days left. Current fare is ₹{price:,} (Typical: {range_str}). Hold until Oct 30 to catch a dip below ₹{TARGET_PRICE:,}.",
    )

def send_whatsapp(body: str):
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    payload = {"From": TWILIO_WHATSAPP_FROM, "To": WHATSAPP_TO, "Body": body}
    resp = requests.post(url, data=payload, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=20)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Twilio API Error ({resp.status_code}): {resp.text}")
    print("WhatsApp alert delivered successfully!")

def main():
    validate_config()
    days_left = (date(2026, 11, 13) - date.today()).days
    data = fetch_flight_data()
    info = parse_best_itinerary(data)
    signal, advice = evaluate_decision(info, days_left)
    card_price = int(info["price"] * 0.88)
    typical_str = f"₹{info['typical_low']:,} – ₹{info['typical_high']:,}" if info["typical_low"] else "N/A"

    message = (
        f"✈️ *KNU → IXE Flight Tracker (13 Nov 2026)*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"*Signal:* {signal}\n"
        f"*Lowest Fare:* ₹{info['price']:,}\n"
        f"*With ~12% Card Promo:* ~₹{card_price:,}\n"
        f"*Google Rating:* {info['price_level'].upper()} (Typical: {typical_str})\n\n"
        f"🛫 *Cheapest Itinerary:*\n"
        f"• *Airline:* {info['airlines']} ({info['flight_nums']})\n"
        f"• *Departs:* {info['dep_time']}\n"
        f"• *Arrives:* {info['arr_time']}\n"
        f"• *Duration:* {info['total_duration']}\n"
        f"• *Layover:* {info['layover']}\n\n"
        f"💡 *Algorithmic Verdict:*\n{advice}\n\n"
        f"🔗 *Book on Cleartrip:*\n{CLEARTRIP_URL}"
    )
    print(message)
    send_whatsapp(message)

if __name__ == "__main__":
    main()
