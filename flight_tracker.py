"""Backward-compatible entry point.

The project is now a proper package (``flighttracker/``). This shim keeps the
old ``python flight_tracker.py`` command working by delegating to the package
CLI. See README.md for the new ``python -m flighttracker`` usage.
"""
from flighttracker.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
