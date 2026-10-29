"""Pack analysis tiles into compact binary pieces (analysis format v3).

Format v2 writes one JSON file per 1x1 km tile. All of Germany would be
far beyond Cloudflare Pages' 20,000 files, so v3 stores the same content
in a binary encoding and packs many tiles into one piece file:

- **Tile blob** (then gzip-compressed on its own, so a tile can be cut out
  of a piece and inflated by itself): every number is a LEB128 varint;
  signed ones are zig-zag encoded. Lengths and coordinates are in
  centimetres, which is exactly the precision v2 stores (two decimals), so
  decoding gives v2's values back bit for bit::

      "BLP3"                        magic
      u  version (3)
      u  tile E, u tile N           km; origin = (E, N) * 1000
      u  function count, then that many strings
      u  building count, then per building:
         str id
         u   function index + 1     0 = no function code
         s   groundZ, s eaveZ - groundZ, s ridgeZ - eaveZ        (cm)
         polygons:  u count > u ring count > ring of (s dx, s dy)
         roofs:     u count > u ring count > ring of (s dx, s dy, s dz)

  A ring starts with ``u (points << 1) | closed``; a closed ring omits its
  last point, which repeats the first. x/y are deltas from the previous
  point of the same building (starting at 0, 0), roof z a delta from the
  previous roof z, relative to groundZ. A string is ``u byte length`` and
  UTF-8.
- **Pieces:** the gzip members, concatenated in Hilbert order of the tiles
  (neighbouring tiles tend to share a piece), cut at about ``PIECE_SIZE``
  bytes without ever splitting a tile. A piece is named after its content
  hash, so unchanged pieces keep their name across releases.
- **Index** ``analysis/index.json``: piece names and, per tile, ``[piece,
  offset, length]`` of its gzip member. The manifest points to it
  (``analysisIndex``).

Usage: ``python -m lod2pipe.pack DIR [--piece-size BYTES]``: packs
DIR/analysis/*.json and updates DIR/manifest.json in place. The JSON tiles
stay, so older app versions keep working.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

from .export import ANALYSIS_FORMAT

PACKED_VERSION = 3
MAGIC = b"BLP3"
# 1 MiB: Germany then needs about 6-10k pieces (Pages allows 20,000 files);
# halving it would roughly double that.
PIECE_SIZE = 1024 * 1024
INDEX_NAME = "analysis/index.json"
PIECE_DIR = "analysis/pieces"
# Hilbert curve side: 2^12 km covers every UTM32 easting and northing - 5000 km.
_HILBERT_ORDER = 1 << 12
_NORTHING_OFFSET_KM = 5000


class _Writer:
    def __init__(self) -> None:
        self.buf = bytearray()

    def u(self, v: int) -> None:
        if v < 0:
            raise ValueError(f"negative unsigned varint {v}")
        while v > 0x7F:
            self.buf.append((v & 0x7F) | 0x80)
            v >>= 7
        self.buf.append(v)

    def s(self, v: int) -> None:
        self.u(v * 2 if v >= 0 else -v * 2 - 1)

    def str(self, text: str) -> None:
        data = text.encode("utf-8")
        self.u(len(data))
        self.buf += data


def _cm(value: float) -> int:
    """Centimetres; refuses values v2 couldn't have written (more than 2 decimals)."""
    cm = round(value * 100)
    if abs(cm / 100 - value) > 1e-6:
        raise ValueError(f"{value} is not on the centimetre grid")
    return cm


def _write_ring(w: _Writer, ring: list, pos: list[int], ground: int, dims: int) -> None:
    closed = len(ring) > 1 and ring[0] == ring[-1]
    points = ring[:-1] if closed else ring
    w.u((len(points) << 1) | int(closed))
    for p in points:
        x, y = _cm(p[0]), _cm(p[1])
        w.s(x - pos[0])
        w.s(y - pos[1])
        pos[0], pos[1] = x, y
        if dims == 3:
            z = _cm(p[2]) - ground
            w.s(z - pos[2])
            pos[2] = z


def _write_multi(w: _Writer, polys: list, ground: int, dims: int, pos: list[int]) -> None:
    w.u(len(polys))
    for rings in polys:
        w.u(len(rings))
        for ring in rings:
            _write_ring(w, ring, pos, ground, dims)


def encode_tile(tile: dict[str, Any]) -> bytes:
    """A v2 analysis tile (as parsed JSON) as an uncompressed v3 blob."""
    e, n = (int(v) for v in tile["tile"].split("_"))
    if list(tile["origin"]) != [e * 1000, n * 1000]:
        raise ValueError(f"tile {tile['tile']}: origin {tile['origin']} doesn't match its key")
    functions = sorted({b["function"] for b in tile["buildings"] if b["function"] is not None})
    function_index = {f: i + 1 for i, f in enumerate(functions)}
    w = _Writer()
    w.buf += MAGIC
    w.u(PACKED_VERSION)
    w.u(e)
    w.u(n)
    w.u(len(functions))
    for f in functions:
        w.str(f)
    w.u(len(tile["buildings"]))
    for b in tile["buildings"]:
        w.str(b["id"])
        w.u(0 if b["function"] is None else function_index[b["function"]])
        ground, eave, ridge = _cm(b["groundZ"]), _cm(b["eaveZ"]), _cm(b["ridgeZ"])
        w.s(ground)
        w.s(eave - ground)
        w.s(ridge - eave)
        pos = [0, 0, 0]
        _write_multi(w, b["polygons"], ground, 2, pos)
        _write_multi(w, b["roofs"], ground, 3, pos)
    return bytes(w.buf)


class _Reader:
    def __init__(self, data: bytes) -> None:
        self.data, self.i = data, 0

    def u(self) -> int:
        v, shift = 0, 0
        while True:
            byte = self.data[self.i]
            self.i += 1
            v |= (byte & 0x7F) << shift
            if byte < 0x80:
                return v
            shift += 7

    def s(self) -> int:
        v = self.u()
        return v >> 1 if v % 2 == 0 else -(v >> 1) - 1

    def str(self) -> str:
        length = self.u()
        text = self.data[self.i : self.i + length].decode("utf-8")
        self.i += length
        return text


def _read_multi(r: _Reader, ground: int, dims: int, pos: list[int]) -> list:
    polys = []
    for _ in range(r.u()):
        rings = []
        for _ in range(r.u()):
            head = r.u()
            ring = []
            for _ in range(head >> 1):
                pos[0] += r.s()
                pos[1] += r.s()
                point = [pos[0] / 100, pos[1] / 100]
                if dims == 3:
                    pos[2] += r.s()
                    point.append((pos[2] + ground) / 100)
                ring.append(point)
            if head & 1:
                ring.append(list(ring[0]))
            rings.append(ring)
        polys.append(rings)
    return polys


def decode_tile(blob: bytes) -> dict[str, Any]:
    """The inverse of encode_tile (the app has its own decoder; this one is for tests)."""
    if blob[:4] != MAGIC:
        raise ValueError("not a v3 analysis tile")
    r = _Reader(blob)
    r.i = 4
    if (version := r.u()) != PACKED_VERSION:
        raise ValueError(f"v3 blob has version {version}")
    e, n = r.u(), r.u()
    functions = [r.str() for _ in range(r.u())]
    buildings = []
    for _ in range(r.u()):
        bid = r.str()
        fi = r.u()
        ground = r.s()
        eave = ground + r.s()
        ridge = eave + r.s()
        pos = [0, 0, 0]
        polygons = _read_multi(r, ground, 2, pos)
        roofs = _read_multi(r, ground, 3, pos)
        buildings.append(
            {
                "id": bid,
                "groundZ": ground / 100,
                "eaveZ": eave / 100,
                "ridgeZ": ridge / 100,
                "function": functions[fi - 1] if fi else None,
                "polygons": polygons,
                "roofs": roofs,
            }
        )
    return {"tile": f"{e}_{n}", "origin": [e * 1000, n * 1000], "buildings": buildings}


def hilbert_index(e: int, n: int) -> int:
    """Position of tile (E, N) km on a Hilbert curve (neighbours stay close)."""
    x, y = e, n - _NORTHING_OFFSET_KM
    if not (0 <= x < _HILBERT_ORDER and 0 <= y < _HILBERT_ORDER):
        raise ValueError(f"tile {e}_{n} outside the Hilbert grid")
    d = 0
    s = _HILBERT_ORDER // 2
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        s //= 2
    return d


def _tile_order(key: str) -> tuple[int, str]:
    e, n = (int(v) for v in key.split("_"))
    return hilbert_index(e, n), key


def compress(blob: bytes) -> bytes:
    # mtime=0: the same tile always gives the same bytes (and piece hash).
    return gzip.compress(blob, compresslevel=9, mtime=0)


def pack_release(directory: Path, piece_size: int = PIECE_SIZE) -> dict[str, Any]:
    """Write the pieces and the index for DIR/analysis/*.json; return the index."""
    tiles = {p.stem: p for p in (directory / "analysis").glob("*.json") if p.name != "index.json"}
    piece_dir = directory / PIECE_DIR
    piece_dir.mkdir(parents=True, exist_ok=True)
    for old in piece_dir.glob("*.bin"):
        old.unlink()
    pieces: list[str] = []
    entries: dict[str, list[int]] = {}
    current = bytearray()
    pending: list[tuple[str, int, int]] = []

    def flush() -> None:
        if not current:
            return
        name = hashlib.sha256(current).hexdigest()[:16] + ".bin"
        (piece_dir / name).write_bytes(current)
        for key, offset, length in pending:
            entries[key] = [len(pieces), offset, length]
        pieces.append(name)
        current.clear()
        pending.clear()

    for key in sorted(tiles, key=_tile_order):
        member = compress(encode_tile(json.loads(tiles[key].read_text(encoding="utf-8"))))
        if current and len(current) + len(member) > piece_size:
            flush()
        pending.append((key, len(current), len(member)))
        current += member
    flush()

    index = {
        "format": ANALYSIS_FORMAT,
        "version": PACKED_VERSION,
        "pieces": pieces,
        "tiles": dict(sorted(entries.items())),
    }
    (directory / INDEX_NAME).write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["analysisIndex"] = INDEX_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    return index


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="lod2pipe.pack", description=__doc__.split("\n")[0])
    p.add_argument("directory", type=Path)
    p.add_argument("--piece-size", type=int, default=PIECE_SIZE)
    args = p.parse_args(argv)
    index = pack_release(args.directory, args.piece_size)
    sizes = [(args.directory / PIECE_DIR / name).stat().st_size for name in index["pieces"]]
    print(
        f"analysis v3: {len(index['tiles'])} tiles in {len(index['pieces'])} pieces, "
        f"{sum(sizes) / 1e6:.1f} MB, largest piece {max(sizes, default=0) / 1024:.0f} KiB"
    )


if __name__ == "__main__":
    main()
