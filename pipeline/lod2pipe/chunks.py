"""Cut PMTiles archives into fixed-size pieces for static hosting.

Cloudflare Pages answers ``Range:`` requests with the whole file and limits
files to 25 MiB, so a release served from Pages stores each archive as
``<archive>.chunks/<index>.bin`` pieces of ``size`` bytes (the last one
shorter). The app reads the pieces that cover a byte range and cuts the
range out (app/src/data/chunkedSource.ts). The manifest records the piece
size and each archive's length; joining the pieces gives the archive back,
so a host with range requests (R2) can serve the whole files instead.

Usage: ``python -m lod2pipe.chunks DIR [--size BYTES] [--keep]``: every
``*.pmtiles`` in DIR, manifest updated in place.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

# 64 KiB: measured on the Köln basemap, typical phone views fetch 9-108 %
# more bytes than exact ranges would; larger pieces cost much more.
DEFAULT_SIZE = 64 * 1024


def chunk_dir(archive: Path) -> Path:
    return archive.with_name(archive.name + ".chunks")


def chunk_name(index: int) -> str:
    return f"{index:06d}.bin"


def split_archive(archive: Path, size: int) -> int:
    """Write the pieces next to the archive; return the archive's length."""
    target = chunk_dir(archive)
    if target.exists():
        shutil.rmtree(target)
    target.mkdir()
    total = 0
    with archive.open("rb") as src:
        index = 0
        while piece := src.read(size):
            (target / chunk_name(index)).write_bytes(piece)
            total += len(piece)
            index += 1
    return total


def chunk_release(directory: Path, size: int = DEFAULT_SIZE, keep: bool = False) -> dict:
    """Split every archive in a release directory and record it in the manifest."""
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archives = {}
    for archive in sorted(directory.glob("*.pmtiles")):
        archives[archive.name] = split_archive(archive, size)
        if not keep:
            archive.unlink()
    manifest["chunks"] = {"size": size, "archives": archives}
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return manifest["chunks"]


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lod2pipe.chunks", description=__doc__)
    p.add_argument("directory", type=Path)
    p.add_argument("--size", type=int, default=DEFAULT_SIZE, help="piece size in bytes")
    p.add_argument("--keep", action="store_true", help="keep the whole archives too")
    args = p.parse_args(argv)
    chunks = chunk_release(args.directory, args.size, args.keep)
    for name, length in chunks["archives"].items():
        count = -(-length // chunks["size"])
        print(f"{name}: {length / 1e6:.1f} MB in {count} pieces of {chunks['size']} bytes")


if __name__ == "__main__":
    main()
