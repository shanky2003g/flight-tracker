"""Command-line entry point."""
from __future__ import annotations

import argparse
import logging
import sys

from .config import load_config
from .notifier.console import ConsoleNotifier
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
        help="Force the console notifier even if Twilio is configured.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    return p


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = load_config(args.config)
    if not config.routes:
        print("ERROR: no routes configured in config.yaml", file=sys.stderr)
        return 2
    if not config.serpapi_key:
        print("ERROR: SERPAPI_KEY environment variable is required.", file=sys.stderr)
        return 2

    provider = SerpApiProvider(config.serpapi_key)

    notifier = None
    if not args.dry_run:
        if args.console or not config.twilio.configured:
            if not config.twilio.configured:
                logging.getLogger(__name__).warning(
                    "Twilio not fully configured; using console notifier."
                )
            notifier = ConsoleNotifier()
        else:
            notifier = TwilioWhatsAppNotifier(config.twilio)

    pipeline = Pipeline(config, provider, notifier, dry_run=args.dry_run)
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
