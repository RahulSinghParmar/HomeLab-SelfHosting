"""Checkout entry point preserving the caller's working directory."""
import sys

if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required; install it manually first.")

from homelab.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
