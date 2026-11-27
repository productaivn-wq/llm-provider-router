"""Module entrypoint for `python -m llm_provider_router`."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
