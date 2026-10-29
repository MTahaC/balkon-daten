"""CLI: ``python -m lod2pipe [--tiles FILE | --bbox ... | --municipality NAME] [--out DIR]``.

Runs the whole pipeline: fetch tiles -> parse prisms -> write analysis
JSON + GeoJSONSeq -> tippecanoe -> PMTiles, then the basemap extract and the
address index for the same tiles, and finally the manifest.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pyproj import Transformer

from . import addresses, basemap
from .export import open_geojsonseq, write_json
from .fetch import load_index
from .pack import shard
from .process import process_tile
from .tiles import BASE_URL, TileId, read_tile_list, tiles_in_bbox, with_neighbours

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = PIPELINE_DIR.parent

PMTILES_NAME = "buildings.pmtiles"
ADDRESSES_NAME = "addresses.json"
LAYER = "buildings"

# Building parts below these footprints are left out of the two most
# zoomed-out levels, where one screen pixel is ~12 m (z13) and ~6 m (z14):
# they hold 42 % of the geometry in Köln (52 % of the parts are < 50 m²)
# and made the city-wide start view load 1.3-2.7 MB of building tiles.
# From z15 every building is drawn.
DISPLAY_FILTER = [
    "any",
    [">=", "$zoom", 15],
    ["all", ["==", "$zoom", 14], [">=", "area", 25]],
    [">=", "area", 50],
]

SOURCE_NAME = "3D-Gebäudemodell LoD2 NRW"
LICENSE_NAME = "Datenlizenz Deutschland – Zero – Version 2.0"
LICENSE_URL = "https://www.govdata.de/dl-de/zero-2-0"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="lod2pipe", description=__doc__)
    sel = p.add_mutually_exclusive_group()
    sel.add_argument(
        "--tiles",
        type=Path,
        default=PIPELINE_DIR / "tiles.txt",
        help="tile list file (default: pipeline/tiles.txt)",
    )
    sel.add_argument(
        "--bbox",
        type=float,
        nargs=4,
        metavar=("MIN_E", "MIN_N", "MAX_E", "MAX_N"),
        help="UTM32 bounding box in metres (EPSG:25832)",
    )
    sel.add_argument(
        "--all",
        action="store_true",
        help="every tile in the portal index (all of NRW); combine with --shard",
    )
    sel.add_argument(
        "--municipality",
        help="every tile with an address in this municipality (Gebäudereferenzen name, "
        'e.g. "Köln") plus one ring of neighbour tiles, so shading near the border is complete',
    )
    p.add_argument(
        "--shard",
        metavar="I/N",
        help="only shard I of N (0-based): consecutive tiles in Hilbert order with "
        "about equal CityGML size, for parallel jobs; each shard packs its own pieces",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=5,
        help="download retries per tile, backing off 2, 4, 8, … s (default: 5)",
    )
    p.add_argument(
        "--release",
        help="data release id; the app then loads the files from releases/<id>/ (R2)",
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=os.cpu_count() or 1,
        help="tiles downloaded and parsed in parallel (default: CPU count)",
    )
    p.add_argument(
        "--delete-downloads",
        action="store_true",
        help="delete each CityGML file once processed (CI disks are small)",
    )
    p.add_argument(
        "--cache",
        type=Path,
        default=PIPELINE_DIR / ".cache",
        help="download cache for CityGML tiles",
    )
    p.add_argument(
        "--work", type=Path, default=PIPELINE_DIR / "out", help="intermediate files (GeoJSONSeq)"
    )
    p.add_argument(
        "--out",
        type=Path,
        default=REPO_DIR / "out" / "release",
        help="release directory (copy or pass the app's public/data/ for local use)",
    )
    p.add_argument(
        "--skip-tiles",
        action="store_true",
        help="do not run tippecanoe (e.g. on Windows without WSL)",
    )
    p.add_argument(
        "--skip-basemap",
        action="store_true",
        help="do not extract the Protomaps basemap (needs the pmtiles CLI and network)",
    )
    p.add_argument(
        "--skip-addresses",
        action="store_true",
        help="do not build the address index (downloads ~100 MB Gebäudereferenzen)",
    )
    return p.parse_args(argv)


def _select_tiles(args: argparse.Namespace, index: dict) -> list[TileId]:
    tiles = _selection(args, set(index))
    if args.shard:
        try:
            i, n = (int(v) for v in args.shard.split("/"))
            keys = set(shard({t.key: index[t.file_name].size for t in tiles}, i, n))
        except ValueError as err:
            sys.exit(f"--shard {args.shard}: {err}")
        tiles = [t for t in tiles if t.key in keys]
    if not tiles:
        sys.exit("No tiles selected")
    return tiles


def _selection(args: argparse.Namespace, available: set[str]) -> list[TileId]:
    if args.all:
        return sorted(TileId.parse(name) for name in available)
    if args.bbox or args.municipality:
        if args.municipality:
            gebref = addresses.read_gebref(addresses.fetch_gebref(args.cache))
            try:
                selected = with_neighbours(addresses.municipality_tiles(gebref, args.municipality))
            except ValueError as err:
                sys.exit(str(err))
        else:
            selected = tiles_in_bbox(*args.bbox)
        # Both may reach outside NRW; tiles without data are simply skipped.
        tiles = [t for t in selected if t.file_name in available]
    else:
        tiles = read_tile_list(args.tiles.read_text(encoding="utf-8"))
        missing = [t.key for t in tiles if t.file_name not in available]
        if missing:
            sys.exit(f"Tiles not in the portal index: {', '.join(missing)}")
    return tiles


def _wgs84_bounds(tiles: list[TileId]) -> list[float]:
    """Lon/lat box around all tiles.

    UTM grid north is rotated against true north (meridian convergence,
    about -1.6 deg around Cologne), so a UTM square is a slightly rotated
    quadrilateral in lon/lat. Taking min/max over all corners covers it.
    """
    t = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)
    lons, lats = [], []
    for tile in tiles:
        x0, y0, x1, y1 = tile.bounds
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1)):
            lon, lat = t.transform(x, y)
            lons.append(lon)
            lats.append(lat)
    return [round(min(lons), 6), round(min(lats), 6), round(max(lons), 6), round(max(lats), 6)]


def _run_tippecanoe(geojsonseq: Path, target: Path, attribution: str) -> None:
    exe = shutil.which("tippecanoe")
    if exe is None:
        sys.exit("tippecanoe not found on PATH; run pipeline/setup.sh or use --skip-tiles")
    cmd = [
        exe,
        "--output",
        str(target),
        "--force",
        "--layer",
        LAYER,
        "--name",
        SOURCE_NAME,
        "--attribution",
        attribution,
        # z13 is the lowest zoom at which individual buildings are readable;
        # z16 keeps geometry detail at ~0.1 m per tile unit.
        "--minimum-zoom",
        "13",
        "--maximum-zoom",
        "16",
        # Never drop buildings by tile size; instead the smallest parts are
        # left out where they are about a pixel or less (DISPLAY_FILTER).
        "--no-feature-limit",
        "--no-tile-size-limit",
        "--feature-filter",
        json.dumps({LAYER: DISPLAY_FILTER}),
        "--read-parallel",
        str(geojsonseq),
    ]
    subprocess.run(cmd, check=True)


def _process_tiles(
    args: argparse.Namespace, tiles: list[TileId], index: dict, geojsonseq: Path
) -> None:
    """All tiles, ``--jobs`` at a time; display features are streamed into
    the GeoJSONSeq file as tiles finish, so memory stays at a few tiles."""
    seen: set[str] = set()
    duplicates = 0

    def unique(features: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        # Defensive: a building listed in two tiles is drawn once. Its analysis
        # record stays in both tiles; duplicate edges don't change a horizon.
        nonlocal duplicates
        for f in features:
            fid = f["properties"]["id"]
            if fid in seen:
                duplicates += 1
                continue
            seen.add(fid)
            yield f

    jobs = [
        (t, args.cache, index[t.file_name].size, args.out, args.delete_downloads, args.retries)
        for t in tiles
    ]
    with open_geojsonseq(geojsonseq) as write:
        if args.jobs <= 1:
            results: Iterable[tuple[str, list[dict[str, Any]]]] = (
                process_tile(*job) for job in jobs
            )
            pool = None
        else:
            pool = ProcessPoolExecutor(max_workers=args.jobs)
            futures = [pool.submit(process_tile, *job) for job in jobs]
            results = (f.result() for f in as_completed(futures))
        try:
            for done, (report, features) in enumerate(results, start=1):
                print(f"[{done}/{len(tiles)}] {report}", flush=True)
                write(unique(features))
        finally:
            if pool:
                pool.shutdown(cancel_futures=True)
    if duplicates:
        print(f"{duplicates} display features skipped as duplicates")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    started = time.monotonic()

    def lap(label: str) -> None:
        print(f"-- {label}: {time.monotonic() - started:.0f} s since start", flush=True)

    index = load_index(args.cache)
    tiles = _select_tiles(args, index)
    total_mb = sum(index[t.file_name].size for t in tiles) / 1e6
    print(f"{len(tiles)} tiles, {total_mb:.0f} MB CityGML, {args.jobs} jobs")

    geojsonseq = args.work / "buildings.geojsonl"
    _process_tiles(args, tiles, index, geojsonseq)
    lap("tiles parsed")

    data_year = max(index[t.file_name].timestamp for t in tiles)[:4]
    attribution = (
        f'<a href="{BASE_URL}" target="_blank" rel="noopener">{SOURCE_NAME}</a>: '
        f'Land NRW ({data_year}), <a href="{LICENSE_URL}" target="_blank" rel="noopener">'
        f"{LICENSE_NAME}</a>"
    )
    manifest = {
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        # Files live under releases/<release>/ on R2; null for a local build.
        "release": args.release,
        # Shown to people outside the data ("Gebäudedaten gibt es bisher für …").
        "coverage": "Nordrhein-Westfalen" if args.all else args.municipality,
        "bounds": _wgs84_bounds(tiles),
        "tiles": [t.key for t in tiles],
        "pmtiles": None if args.skip_tiles else PMTILES_NAME,
        "analysisPath": "analysis/{tile}.json",
        "attribution": attribution,
        "basemap": None if args.skip_basemap else basemap.PMTILES_NAME,
        "basemapAttribution": None if args.skip_basemap else basemap.ATTRIBUTION,
        "addresses": None if args.skip_addresses else ADDRESSES_NAME,
    }

    if not args.skip_tiles:
        target = args.out / PMTILES_NAME
        _run_tippecanoe(geojsonseq, target, attribution)
        if pmtiles := shutil.which("pmtiles"):
            subprocess.run([pmtiles, "verify", str(target)], check=True)
        print(f"{target.name}: {target.stat().st_size / 1e6:.1f} MB")
        lap("buildings.pmtiles")
    if not args.skip_basemap:
        target = args.out / basemap.PMTILES_NAME
        basemap.run_extract(tiles, target, args.work)
        print(f"{target.name}: {target.stat().st_size / 1e6:.1f} MB (build {basemap.BUILD})")
        lap("basemap")
    if not args.skip_addresses:
        found = list(
            addresses.in_tiles(addresses.read_gebref(addresses.fetch_gebref(args.cache)), tiles)
        )
        address_index = addresses.build_index(found, tiles)
        write_json(args.out / ADDRESSES_NAME, address_index)
        print(
            f"{ADDRESSES_NAME}: {len(found)} addresses in {len(address_index['streets'])} streets"
        )
        lap("addresses")
    write_json(args.out / "manifest.json", manifest)


if __name__ == "__main__":
    main()
