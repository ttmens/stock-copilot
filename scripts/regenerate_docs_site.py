#!/usr/bin/env python3
"""Regenerate static site in site/ and sync to docs/ from existing latest.json."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.site.generator import generate_site, report_from_latest_json


def main() -> None:
    latest = ROOT / "docs" / "data" / "latest.json"
    if not latest.is_file():
        latest = ROOT / "site" / "data" / "latest.json"
    if not latest.is_file():
        raise SystemExit(f"No latest.json found under docs/data or site/data")

    report = report_from_latest_json(latest)
    path = generate_site(report)
    print(f"Site regenerated: {path}")


if __name__ == "__main__":
    main()
