"""Naming and extent of the NRW LoD2 1x1 km tiles.

Tiles are named ``LoD2_32_<E>_<N>_1_NW.gml`` where ``32`` is the UTM zone,
``E``/``N`` are the easting/northing of the tile's lower-left corner in
kilometres (EPSG:25832, ETRS89 / UTM zone 32N) and ``1`` is the edge length
in km. We use the short key ``"<E>_<N>"`` (e.g. ``"356_5644"``) internally.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

BASE_URL = "https://www.opengeodata.nrw.de/produkte/geobasis/3dg/lod2_gml/lod2_gml/"
INDEX_URL = BASE_URL + "index.json"

TILE_SIZE_M = 1000

_KEY_RE = re.compile(r"^(\d{3})_(\d{4})$")
_FILE_RE = re.compile(r"^LoD2_32_(\d{3})_(\d{4})_1_NW\.gml$")


@dataclass(frozen=True, order=True)
class TileId:
    e_km: int
    n_km: int

    @classmethod
    def parse(cls, text: str) -> TileId:
        """Accept either the short key ``356_5644`` or the full file name."""
        text = text.strip()
        m = _KEY_RE.match(text) or _FILE_RE.match(text)
        if not m:
            raise ValueError(f"Not a LoD2 tile key or file name: {text!r}")
        return cls(int(m.group(1)), int(m.group(2)))

    @classmethod
    def containing(cls, easting: float, northing: float) -> TileId:
        """The tile containing a UTM32 point (metres)."""
        return cls(math.floor(easting / TILE_SIZE_M), math.floor(northing / TILE_SIZE_M))

    @property
    def key(self) -> str:
        return f"{self.e_km:03d}_{self.n_km:04d}"

    @property
    def file_name(self) -> str:
        return f"LoD2_32_{self.key}_1_NW.gml"

    @property
    def url(self) -> str:
        return BASE_URL + self.file_name

    @property
    def origin(self) -> tuple[int, int]:
        """Lower-left corner in EPSG:25832 metres."""
        return self.e_km * TILE_SIZE_M, self.n_km * TILE_SIZE_M

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """(min_e, min_n, max_e, max_n) in EPSG:25832 metres."""
        e, n = self.origin
        return e, n, e + TILE_SIZE_M, n + TILE_SIZE_M


def tiles_in_bbox(min_e: float, min_n: float, max_e: float, max_n: float) -> list[TileId]:
    """All tiles intersecting a UTM32 bounding box (metres), sorted.

    A box edge lying exactly on a tile boundary does not pull in the
    neighbouring tile (half-open intervals).
    """
    if min_e >= max_e or min_n >= max_n:
        raise ValueError("Empty bounding box")
    e0 = math.floor(min_e / TILE_SIZE_M)
    n0 = math.floor(min_n / TILE_SIZE_M)
    e1 = math.ceil(max_e / TILE_SIZE_M)
    n1 = math.ceil(max_n / TILE_SIZE_M)
    return [TileId(e, n) for e in range(e0, e1) for n in range(n0, n1)]


def with_neighbours(tiles: Iterable[TileId], rings: int = 1) -> list[TileId]:
    """The tiles plus every tile up to ``rings`` tiles away from one, sorted.

    One ring (1 km) covers the 300 m shading radius plus the 100 m margin for
    every point inside the original tiles.
    """
    return sorted(
        {
            TileId(t.e_km + de, t.n_km + dn)
            for t in tiles
            for de in range(-rings, rings + 1)
            for dn in range(-rings, rings + 1)
        }
    )


def read_tile_list(text: str) -> list[TileId]:
    """Parse a tile list file: one key per line, ``#`` starts a comment."""
    tiles: list[TileId] = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            tiles.append(TileId.parse(line))
    return sorted(set(tiles))
