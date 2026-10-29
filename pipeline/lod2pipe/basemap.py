"""Self-hosted basemap: a Protomaps (OpenStreetMap) extract around the data.

``pmtiles extract`` reads only the needed byte ranges of a planet build on
build.protomaps.com and writes a small PMTiles archive, which the app
serves itself (no third-party map requests from the browser). The build
date is pinned so deploys are reproducible; bump it to refresh the map.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from pyproj import Transformer
from shapely import box, union_all
from shapely.geometry import mapping
from shapely.ops import transform

from .tiles import TileId

BUILD = "20261025"
BUILD_URL = f"https://build.protomaps.com/{BUILD}.pmtiles"
PMTILES_NAME = "basemap.pmtiles"
# Streets and labels around the buildings, so people recognise where they are.
MARGIN_M = 2000
# MapLibre overzooms beyond this. Compared side by side for Köln (Phase 7a),
# z14 looks the same from z16 on and lacks only a few footpaths and minor
# labels at z15, at 18 MB instead of 45 MB.
MAX_ZOOM = 14
ATTRIBUTION = (
    '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">'
    "© OpenStreetMap-Mitwirkende</a> (ODbL), "
    '<a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a>'
)


def extract_region(tiles: list[TileId], margin_m: float = MARGIN_M) -> dict[str, Any]:
    """GeoJSON (WGS84) of the processed tiles' outline plus a margin.

    Follows the shape of the data instead of its bounding box: for a city
    the box would also pull in the neighbouring towns' map. The outline is
    built in UTM metres (square corners, mitre joins) and simplified to
    100 m, far below the margin, so the extract stays a superset of the data.
    """
    utm = union_all([box(*t.bounds) for t in tiles])
    region = utm.buffer(margin_m, join_style="mitre").simplify(100)
    to_wgs84 = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True).transform
    # Straight UTM edges are very slightly curved in lon/lat; points every
    # 500 m keep the error in the centimetre range.
    return mapping(transform(to_wgs84, region.segmentize(500)))


def extract_command(pmtiles: str, region_path: Path, target: Path) -> list[str]:
    return [
        pmtiles,
        "extract",
        BUILD_URL,
        str(target),
        f"--region={region_path}",
        f"--maxzoom={MAX_ZOOM}",
    ]


def run_extract(tiles: list[TileId], target: Path, work: Path) -> None:
    exe = shutil.which("pmtiles")
    if exe is None:
        sys.exit("pmtiles not found on PATH; run pipeline/setup.sh or use --skip-basemap")
    target.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    region_path = work / "basemap-region.geojson"
    region_path.write_text(json.dumps(extract_region(tiles)), encoding="utf-8")
    subprocess.run(extract_command(exe, region_path, target), check=True)
    subprocess.run([exe, "verify", str(target)], check=True)
