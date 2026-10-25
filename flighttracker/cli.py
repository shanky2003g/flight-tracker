"""Command-line entry point."""
from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .notifier.console import ConsoleNotifier
from .notifier.telegram import TelegramNotifier
from .notifier.whatsapp import TwilioWhatsAppNotifier
from .pipeline import Pipeline
from .providers.serpapi import SerpApiProvider


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="flighttracker",
        description="Track fares, decide if it is a good time to book, and alert on WhatsApp.",
    )
    p.add_argument("-c", "--config", default="config.yaml", help="Path to config.yaml")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and analyze but do not write history or send WhatsApp (prints instead).",
    )
    p.add_argument(
        "--console",
        action="store_true",
        help="Force the console notifier even if a real channel is configured.",
    )
    p.add_argument(
        "--channel",
        choices=["auto", "telegram", "whatsapp", "console"],
        default="auto",
        help="Which notifier to use. 'auto' prefers Telegram, then WhatsApp, else console.",
    )
    p.add_argument(
        "--force-alert",
        action="store_true",
        help="Send the alert now regardless of the time window / signal (for testing delivery).",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")

    override = p.add_argument_group(
        "one-off route override",
        "Check a specific route for this run instead of the ones in config.yaml. "
        "Requires --origin, --destination and --date together.",
    )
    override.add_argument("--origin", help="Origin airport IATA code, e.g. KNU")
    override.add_argument("--destination", help="Destination airport IATA code, e.g. BOM")
    override.add_argument("--date", help="Departure date, YYYY-MM-DD")
    override.add_argument("--currency", default="INR", help="Currency code (default INR)")
    override.add_argument(
        "--target-price", type=int, default=None, help="Optional target price for the override route."
    )
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)

    # One-off route override (e.g. from the GitHub Actions "Run workflow" form).
    if any([args.origin, args.destination, args.date]):
        if not all([args.origin, args.destination, args.date]):
            print(
                "ERROR: --origin, --destination and --date must be given together.",
                file=sys.stderr,
            )
            return 2
        from .models import Route

        config.routes = [
            Route(
                origin=args.origin.upper(),
                destination=args.destination.upper(),
                departure_date=args.date,
                currency=args.currency.upper(),
                target_price=args.target_price,
            )
        ]
        logging.getLogger(__name__).info(
            "One-off override route: %s", config.routes[0].label
        )

    if not config.routes:
        print("ERROR: no routes configured in config.yaml", file=sys.stderr)
        return 2
    if not config.serpapi_key:
        print("ERROR: SERPAPI_KEY environment variable is required.", file=sys.stderr)
        return 2

    provider = SerpApiProvider(config.serpapi_key)

    notifier = None
    if not args.dry_run:
        log = logging.getLogger(__name__)
        channel = "console" if args.console else args.channel
        if channel == "auto":
            if config.telegram.configured:
                channel = "telegram"
            elif config.twilio.configured:
                channel = "whatsapp"
            else:
                channel = "console"

        if channel == "telegram":
            if not config.telegram.configured:
                log.warning("Telegram not configured; using console notifier.")
                notifier = ConsoleNotifier()
            else:
                notifier = TelegramNotifier(config.telegram)
        elif channel == "whatsapp":
            if not config.twilio.configured:
                log.warning("Twilio not configured; using console notifier.")
                notifier = ConsoleNotifier()
            else:
                notifier = TwilioWhatsAppNotifier(config.twilio)
        else:
            notifier = ConsoleNotifier()

    pipeline = Pipeline(
        config, provider, notifier, dry_run=args.dry_run, force_alert=args.force_alert
    )
    results = pipeline.run()

    exit_code = 0
    for r in results:
        if r.error:
            exit_code = 1
            print(f"[{r.route.label}] ERROR: {r.error}", file=sys.stderr)
        elif r.decision:
            flag = f" -> ALERT ({r.alert_kind})" if r.alerted else ""
            print(
                f"[{r.route.label}] {r.decision.signal.value} "
                f"({r.decision.confidence}) @ {r.quote.price}{flag}"
            )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
