# ✈️ Flight Tracker

Continuously tracks a flight fare, records a **price history**, and uses that
full history to decide whether **now is a good time to book** — then sends a
WhatsApp alert. Built to run for free on GitHub Actions.

Default route: **Kanpur (KNU) → Mangalore (IXE)**, 13 Nov 2026. Everything is
configurable in [`config.yaml`](config.yaml); nothing is hardcoded.

---

## Why this is more than a price checker

The original script was *stateless*: every run saw only the current price, so it
could never tell whether that price was actually good. This version **persists
every observation** and makes a transparent, multi-signal decision:

| Signal | What it measures |
| --- | --- |
| **Relative price** | Percentile rank of today's fare in the full history; ties/beats all-time low |
| **Trend** | Least-squares slope over a recent window — is the fare rising or falling now? |
| **Time pressure** | Days to departure; thin connecting fares rarely drop in the final stretch |
| **Market context** | Google's own `price_level` and typical range |

These combine into one verdict — `STRONG_BUY`, `BUY`, `URGENT`, `WAIT`, or
`COLLECTING` (cold start) — with a confidence level and a plain-English
explanation of *why*.

## Alerts (no spam)

- **One evening digest per day** with the current price and verdict.
- **Immediate** alerts for a **strong-buy** or a **new all-time low**, deduped by
  a cooldown so you never get spammed.

Tune all of this under `alerts:` in `config.yaml`.

---

## Architecture

```
flighttracker/
  config.py            # YAML settings + secrets from env
  models.py            # typed dataclasses (Route, Quote, Decision, ...)
  providers/           # pluggable fare sources (SerpApi Google Flights)
  storage.py           # append-only JSONL history + JSON alert state
  analyzer.py          # the decision algorithm (reads full history)
  alerting.py          # when/why to actually send
  notifier/            # WhatsApp (Twilio) + console
  messages.py          # human-readable message formatting
  pipeline.py          # fetch -> record -> analyze -> decide -> notify
  cli.py               # command-line entry point
data/                  # price_history.jsonl + alert_state.json (committed by CI)
tests/                 # offline unit tests with a saved fixture
```

History is stored as **append-only JSONL** — human-readable and git-diff
friendly. Because GitHub Actions runners are ephemeral, the workflow commits the
updated `data/` files back to the repo after each run, so history survives.

---

## Setup

### 1. Secrets (never put these in `config.yaml`)

Set as environment variables locally, or as **GitHub Actions secrets**:

| Variable | Purpose |
| --- | --- |
| `SERPAPI_KEY` | [SerpApi](https://serpapi.com/) key for Google Flights |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_WHATSAPP_FROM` | Twilio WhatsApp sender (e.g. `whatsapp:+14155238886`) |
| `WHATSAPP_TO` | Your WhatsApp number (e.g. `whatsapp:+91XXXXXXXXXX`) |
| `TWILIO_CONTENT_SID` | *(optional)* approved template SID for the 24h-window fallback |

### 2. Install

```bash
pip install -r requirements.txt
# or, for development (tests):
pip install -r requirements-dev.txt
```

### 3. Run

```bash
# Real run (fetches, records history, sends WhatsApp if a trigger fires)
python -m flighttracker

# Safe preview: fetch + analyze, print the message, but DON'T persist or send
python -m flighttracker --dry-run

# Force the console notifier even if Twilio is configured
python -m flighttracker --console -v
```

> The legacy `python flight_tracker.py` command still works (it delegates to the
> package).

### 4. Automate (GitHub Actions)

`.github/workflows/flight_tracker.yml` runs every 6 hours, sends alerts, and
commits the updated history. Add the secrets above under
**Settings → Secrets and variables → Actions**.

---

## Configuring routes

Edit `config.yaml`. To track a different or additional route, just add entries:

```yaml
routes:
  - origin: KNU
    destination: IXE
    departure_date: 2026-11-13
    currency: INR
    target_price: null      # null = let the algorithm decide from history
  - origin: DEL
    destination: BOM
    departure_date: 2026-12-01
    currency: INR
```

---

## Tests

```bash
python -m pytest
```

All tests run **offline** (a saved SerpApi fixture + fake providers), so no API
keys or network are needed.
