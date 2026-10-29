"""Address index for the app's search, from the NRW Gebäudereferenzen.

Source: ``gebref_EPSG25832_ASCII.zip`` on opengeodata.nrw.de (ALKIS main
buildings with house numbers, statewide, dl-de/zero-2-0). One record per
line, ``;``-separated, UTF-8. Fields used (0-based, checked against the
2026-07 file):

    1 id   2 quality (A = point inside the building)   10 municipality
    13 street key   14 street name ("Gilbachstr.")   15 house number
    16 suffix ("a")   18 easting   19 northing (EPSG:25832, metres)

The app gets only the addresses inside the processed LoD2 tiles: there is
nothing to place a balcony on elsewhere.
"""

from __future__ import annotations

import difflib
import hashlib
import io
import json
import re
import shutil
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from .export import write_json
from .fetch import _open
from .tiles import TileId

PORTAL_URL = "https://www.opengeodata.nrw.de/produkte/geobasis/lk/akt/gebref_txt/"
ZIP_NAME = "gebref_EPSG25832_ASCII.zip"
SOURCE_NAME = "Gebäudereferenzen NRW"
FORMAT = "balkon-addresses"
VERSION = 1

_STR_WORD = re.compile(r"\bStr\.")
_STR_SUFFIX = re.compile(r"(?<=[a-zäöüß])str\.")


@dataclass(frozen=True)
class Address:
    municipality: str
    street: str
    number: str
    suffix: str
    e: float
    n: float


def display_street(name: str) -> str:
    """Expand ALKIS' "Str." abbreviations: "Aachener Str." -> "Aachener Straße",
    "Gilbachstr." -> "Gilbachstraße". "St." (Sankt) and "Dr." stay as written."""
    return _STR_SUFFIX.sub("straße", _STR_WORD.sub("Straße", name))


def parse_line(line: str) -> Address | None:
    """One Gebäudereferenzen record, or None for lines that are not addresses."""
    f = line.rstrip("\r\n").split(";")
    if len(f) < 20 or not f[15]:
        return None
    try:
        e, n = float(f[18]), float(f[19])
    except ValueError:
        return None
    return Address(f[10], display_street(f[14]), f[15], f[16], e, n)


def municipality_tiles(addresses: Iterable[Address], name: str) -> list[TileId]:
    """Tiles containing at least one address of the municipality (exact
    Gebäudereferenzen name, e.g. "Köln"), sorted. Tiles on the border also
    contain parts of the neighbouring municipalities."""
    tiles: set[TileId] = set()
    names: set[str] = set()
    for a in addresses:
        names.add(a.municipality)
        if a.municipality == name:
            tiles.add(TileId.containing(a.e, a.n))
    if not tiles:
        close = difflib.get_close_matches(name, sorted(names), n=5)
        hint = f"; did you mean {', '.join(close)}?" if close else ""
        raise ValueError(f"No addresses in municipality {name!r}{hint}")
    return sorted(tiles)


def in_tiles(addresses: Iterable[Address], tiles: Iterable[TileId]) -> Iterator[Address]:
    keys = {t.key for t in tiles}
    return (a for a in addresses if TileId.containing(a.e, a.n).key in keys)


def _number_key(number: str, suffix: str) -> tuple[int, str]:
    return (int(number) if number.isdigit() else 0, suffix)


def build_index(addresses: Iterable[Address], tiles: list[TileId]) -> dict:
    """Compact JSON: streets with their house numbers, coordinates relative to
    the lower-left corner of all tiles (dm precision is plenty for a search)."""
    origin_e = min(t.origin[0] for t in tiles)
    origin_n = min(t.origin[1] for t in tiles)
    streets: dict[tuple[str, str], dict[tuple[str, str], tuple[float, float]]] = {}
    for a in addresses:
        numbers = streets.setdefault((a.street, a.municipality), {})
        numbers[(a.number, a.suffix)] = (round(a.e - origin_e, 1), round(a.n - origin_n, 1))
    return {
        "format": FORMAT,
        "version": VERSION,
        "crs": "EPSG:25832",
        "origin": [origin_e, origin_n],
        # [street, municipality, [[number, suffix, x, y], ...]]
        "streets": [
            [
                street,
                municipality,
                [
                    [num, suf, x, y]
                    for (num, suf), (x, y) in sorted(
                        numbers.items(), key=lambda item: _number_key(*item[0])
                    )
                ],
            ]
            for (street, municipality), numbers in sorted(streets.items())
        ],
    }


def fetch_gebref(cache_dir: Path) -> Path:
    """The statewide zip (~100 MB), re-downloaded when the portal's size changes."""
    with _open(PORTAL_URL + "index.json") as resp:
        files = json.load(resp)["datasets"][0]["files"]
    expected = next(int(f["size"]) for f in files if f["name"] == ZIP_NAME)
    target = cache_dir / ZIP_NAME
    if target.exists() and target.stat().st_size == expected:
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(".part")
    with _open(PORTAL_URL + ZIP_NAME) as resp, partial.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    if partial.stat().st_size != expected:
        partial.unlink()
        raise OSError(f"{ZIP_NAME}: size differs from the portal index")
    partial.replace(target)
    return target


def read_gebref(zip_path: Path) -> Iterator[Address]:
    with zipfile.ZipFile(zip_path) as z, z.open("gebref.txt") as raw:
        for line in io.TextIOWrapper(raw, encoding="utf-8"):
            if (a := parse_line(line)) is not None:
                yield a


STREETS_FORMAT = "balkon-streets"
STREETS_VERSION = 1
STREETS_NAME = "addresses/streets.json"


def write_split(addresses: Iterable[Address], out: Path) -> dict:
    """The address index split for a whole state: OUT/addresses/streets.json
    lists every municipality (name, house-number file, bounding box in
    EPSG:25832) with its street names; OUT/addresses/<hash>.json holds one
    municipality's house numbers in the single-file format (build_index).
    The app loads the street list first and a municipality's numbers only
    when they are needed. Returns the street list."""
    by_town: dict[str, list[Address]] = {}
    for a in addresses:
        by_town.setdefault(a.municipality, []).append(a)
    folder = out / "addresses"
    folder.mkdir(parents=True, exist_ok=True)
    towns = []
    for name, found in sorted(by_town.items()):
        tiles = sorted({TileId.containing(a.e, a.n) for a in found})
        data = json.dumps(
            build_index(found, tiles), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        # Content-hashed like the analysis pieces: immutable, cacheable.
        file = f"{hashlib.sha256(data).hexdigest()[:16]}.json"
        (folder / file).write_bytes(data)
        es, ns = [a.e for a in found], [a.n for a in found]
        towns.append(
            [
                name,
                file,
                [round(min(es)), round(min(ns)), round(max(es)), round(max(ns))],
                sorted({a.street for a in found}),
            ]
        )
    streets = {
        "format": STREETS_FORMAT,
        "version": STREETS_VERSION,
        "crs": "EPSG:25832",
        # [municipality, numbers file (next to this file), [minE, minN, maxE, maxN], [street, …]]
        "municipalities": towns,
    }
    write_json(out / STREETS_NAME, streets)
    return streets
