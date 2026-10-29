"""Per-tile work of the pipeline: fetch, parse, write the analysis tile."""

from __future__ import annotations

import statistics
from pathlib import Path
from typing import Any

from .citygml import ParseStats, Prism, parse_prisms
from .export import analysis_tile, display_feature, write_json
from .fetch import fetch_tile
from .tiles import TileId


def process_tile(
    tile: TileId, cache: Path, size: int, out: Path, delete_download: bool
) -> tuple[str, list[dict[str, Any]]]:
    """Fetch and parse one tile, write its analysis JSON; return the report
    line and the display features. Runs in a worker process,
    so it lives outside ``__main__`` (spawned workers must be able to import it)."""
    path = fetch_tile(tile, cache, size)
    stats = ParseStats()
    prisms = list(parse_prisms(path, stats))
    write_json(out / "analysis" / f"{tile.key}.json", analysis_tile(tile, prisms))
    if delete_download:
        path.unlink()
    features = [f for p in prisms if (f := display_feature(p)) is not None]
    return _report(tile, prisms, stats), features


def _report(tile: TileId, prisms: list[Prism], stats: ParseStats) -> str:
    """Data-quality numbers worth eyeballing for each tile."""
    x0, y0, x1, y1 = tile.bounds
    # Buildings are assigned to one tile but are not clipped at its edge;
    # the app must load neighbour tiles with a margin (see docs/architecture.md).
    overhang = sum(
        1
        for p in prisms
        if (b := p.footprint.bounds)[0] < x0 or b[1] < y0 or b[2] > x1 or b[3] > y1
    )
    # measuredHeight (from the source) should match ridge - ground.
    diffs = [abs(p.measured_height - p.height) for p in prisms if p.measured_height is not None]
    return (
        f"{tile.key}: {stats.buildings} buildings -> {len(prisms)} prisms | "
        f"max h {max((p.height for p in prisms), default=0):.1f} m | "
        f"footprint from roof {stats.footprint_from_roof} | "
        f"skipped no roof {stats.skipped_no_roof}, empty {stats.skipped_empty_footprint} | "
        f"crossing tile edge {overhang} | "
        f"|measuredHeight - h| median {statistics.median(diffs) if diffs else 0:.2f} m, "
        f"max {max(diffs, default=0):.2f} m"
    )
