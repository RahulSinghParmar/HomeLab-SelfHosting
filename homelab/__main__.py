import sys

if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required; no software will be installed automatically.")

from .cli import main

raise SystemExit(main())
