"""Merge packed shards (``lod2pipe --shard`` + ``lod2pipe.pack``) into one release.

Each shard directory holds ``manifest.json`` and ``analysis/index.json`` with
``analysis/pieces/*.bin``. The release gets every piece, one index (piece
numbers renumbered) and one manifest. The manifest lists no tiles: with
all of NRW that would be ~35,000 keys the app loads on every start; the
app takes the tile list from the analysis index instead (``tiles`` empty,
``tilesFromIndex`` true).

With ``--addresses CACHE`` the statewide address index is added, split per
municipality (``addresses.write_split``).

Usage: ``python -m lod2pipe.merge OUT SHARD_DIR... [--release ID] [--addresses CACHE]``
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from . import addresses
from .export import ANALYSIS_FORMAT
from .pack import INDEX_NAME, PACKED_VERSION, PIECE_DIR


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def merge_shards(out: Path, shards: list[Path]) -> dict[str, Any]:
    """Write the merged release into OUT; return its manifest."""
    if not shards:
        raise ValueError("no shards")
    piece_dir = out / PIECE_DIR
    piece_dir.mkdir(parents=True, exist_ok=True)
    pieces: list[str] = []
    tiles: dict[str, list[int]] = {}
    manifests = []
    for shard in shards:
        index = _read(shard / INDEX_NAME)
        if index["format"] != ANALYSIS_FORMAT or index["version"] != PACKED_VERSION:
            raise ValueError(f"{shard}: not a v3 analysis index")
        base = len(pieces)
        for name in index["pieces"]:
            # Content-hashed names: the same name is the same bytes.
            if not (piece_dir / name).exists():
                shutil.copyfile(shard / PIECE_DIR / name, piece_dir / name)
        pieces.extend(index["pieces"])
        for key, (piece, offset, length) in index["tiles"].items():
            if key in tiles:
                raise ValueError(f"tile {key} in two shards")
            tiles[key] = [base + piece, offset, length]
        manifests.append(_read(shard / "manifest.json"))

    (out / INDEX_NAME).write_text(
        json.dumps(
            {
                "format": ANALYSIS_FORMAT,
                "version": PACKED_VERSION,
                "pieces": pieces,
                "tiles": dict(sorted(tiles.items())),
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    first = manifests[0]
    bounds = [m["bounds"] for m in manifests]
    # The newest data year of any shard (the attribution names one year).
    attribution = max((m["attribution"] for m in manifests), key=_year)
    manifest = {
        **first,
        "generatedAt": max(m["generatedAt"] for m in manifests),
        "bounds": [
            min(b[0] for b in bounds),
            min(b[1] for b in bounds),
            max(b[2] for b in bounds),
            max(b[3] for b in bounds),
        ],
        "tiles": [],
        "tilesFromIndex": True,
        "attribution": attribution,
        "analysisIndex": INDEX_NAME,
    }
    return manifest


def _year(attribution: str) -> str:
    # "...: Land NRW (2026), ..." – the year in parentheses.
    start = attribution.find("(")
    return attribution[start + 1 : start + 5] if start >= 0 else ""


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lod2pipe.merge", description=__doc__.split("\n")[0])
    p.add_argument("out", type=Path)
    p.add_argument("shards", type=Path, nargs="+")
    p.add_argument("--release", help="data release id written into the manifest")
    p.add_argument(
        "--addresses",
        type=Path,
        metavar="CACHE",
        help="add the address index split per municipality (Gebäudereferenzen cached here)",
    )
    args = p.parse_args(argv)
    manifest = merge_shards(args.out, sorted(args.shards))
    if args.release:
        manifest["release"] = args.release
    manifest["addresses"] = None
    if args.addresses:
        found = addresses.read_gebref(addresses.fetch_gebref(args.addresses))
        streets = addresses.write_split(found, args.out)
        manifest["addressStreets"] = addresses.STREETS_NAME
        towns = streets["municipalities"]
        print(f"addresses: {len(towns)} municipalities, {sum(len(t[3]) for t in towns)} streets")
    (args.out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    index = _read(args.out / INDEX_NAME)
    print(
        f"merged {len(args.shards)} shards: "
        f"{len(index['tiles'])} tiles, {len(index['pieces'])} pieces"
    )


if __name__ == "__main__":
    main()
