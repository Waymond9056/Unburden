#!/usr/bin/env python3
"""Generate synthetic seed PDFs without starting the API."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.seed import generate_seed_pdfs  # noqa: E402


def main() -> None:
    created = generate_seed_pdfs()
    for item in created:
        print(f"Wrote {item['path']}")
    print(f"Generated {len(created)} seed PDFs")


if __name__ == "__main__":
    main()
