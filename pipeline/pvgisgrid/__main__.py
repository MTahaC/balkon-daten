"""CLI: ``python -m pvgisgrid [--out FILE]``.

Queries PVGIS for the NRW grid (~1300 requests, ~5 minutes) and writes the
JSON the app ships. Run manually when PVGIS publishes a new version; the
result is committed, not rebuilt on every deploy.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from .grid import build_grid

REPO_DIR = Path(__file__).resolve().parent.parent.parent


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="pvgisgrid", description=__doc__)
    p.add_argument("--out", type=Path, default=REPO_DIR / "out" / "pvgis-nrw.json")
    args = p.parse_args(argv)

    def progress(done: int, total: int) -> None:
        if done % 50 == 0 or done == total:
            print(f"{done}/{total}", file=sys.stderr, flush=True)

    grid = build_grid(progress=progress)
    grid["generatedAt"] = datetime.now(UTC).isoformat(timespec="seconds")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(grid, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1000:.0f} kB)")


if __name__ == "__main__":
    main()
