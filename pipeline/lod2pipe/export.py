"""Serialise prisms for the two consumers in the app.

1. **Display** (map): GeoJSON features in WGS84 (EPSG:4326), turned into
   vector tiles by tippecanoe. Tiling quantises and simplifies geometry,
   which is fine for drawing but not for geometry calculations.
2. **Analysis** (shading): one JSON file per 1x1 km tile with exact metric
   coordinates in EPSG:25832, relative to the tile's lower-left corner. The
   horizon ray casting in the app works directly in these metres, so the app
   needs no map projection maths for it. Version 2 adds the 3D roof
   polygons, from which the app computes the horizon exactly.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import Transformer
from shapely import MultiPolygon, Polygon
from shapely.geometry import mapping
from shapely.geometry.polygon import orient

from .citygml import Prism
from .tiles import TileId

ANALYSIS_FORMAT = "balkon-lod2-prisms"
ANALYSIS_VERSION = 2

# 7 decimal places of a degree are ~1 cm on the ground, more than LoD2 offers.
_WGS84_DIGITS = 7
# Analysis coordinates are metres; centimetres are LoD2's own precision.
_METRE_DIGITS = 2

# always_xy: (easting, northing) -> (lon, lat), not the CRS's own axis order.
_TO_WGS84 = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True)


def to_wgs84(geom: Polygon | MultiPolygon) -> Polygon | MultiPolygon:
    def transform(xy: np.ndarray) -> np.ndarray:
        lon, lat = _TO_WGS84.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([lon, lat])

    return shapely.transform(geom, transform)


def _round(coords: Any, ndigits: int) -> Any:
    if isinstance(coords, (float, int)):
        return round(coords, ndigits)
    return [_round(c, ndigits) for c in coords]


def snapped_polygons(geom: Polygon | MultiPolygon, ndigits: int) -> list:
    """MultiPolygon coordinates on a 10^-ndigits grid, still valid.

    Rounding every vertex independently can make a polygon invalid: two
    rings a few millimetres apart (narrow courtyards, adjoining wings) end up
    touching or crossing. On the Cologne test tiles this happened to about
    1 in 1,400 footprints. GEOS's precision reducer (set_precision) snaps to
    the grid *and* repairs the topology, so ray casting later never sees
    self-intersecting rings. Polygons that collapse entirely are dropped.
    """
    snapped = shapely.set_precision(geom, 10.0**-ndigits)
    parts = snapped.geoms if isinstance(snapped, MultiPolygon) else [snapped]
    return [
        _round(mapping(orient(p, sign=1.0))["coordinates"], ndigits)
        for p in parts
        if isinstance(p, Polygon) and not p.is_empty
    ]


def display_feature(prism: Prism) -> dict[str, Any] | None:
    """GeoJSON feature for the map; heights relative to ground in metres."""
    polygons = snapped_polygons(to_wgs84(prism.footprint), _WGS84_DIGITS)
    if not polygons:
        return None
    if len(polygons) == 1:
        geometry = {"type": "Polygon", "coordinates": polygons[0]}
    else:
        geometry = {"type": "MultiPolygon", "coordinates": polygons}
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "id": prism.id,
            "h": round(prism.height, 1),
            "h_eave": round(prism.eave_height, 1),
            "roof": prism.roof_type,
            "fn": prism.function,
            # Footprint in m², for dropping the smallest parts at low zooms.
            "area": round(prism.footprint.area),
        },
    }


def analysis_record(prism: Prism, tile: TileId) -> dict[str, Any] | None:
    ox, oy = tile.origin
    local = shapely.transform(prism.footprint, lambda xy: xy - (ox, oy))
    polygons = snapped_polygons(local, _METRE_DIGITS)
    if not polygons:
        return None
    return {
        "id": prism.id,
        "groundZ": round(prism.ground_z, _METRE_DIGITS),
        "eaveZ": round(prism.eave_z, _METRE_DIGITS),
        "ridgeZ": round(prism.ridge_z, _METRE_DIGITS),
        "function": prism.function,
        # MultiPolygon coordinates: polygons > rings > [x, y], rings closed.
        "polygons": polygons,
        # Roof faces > rings > [x, y, z], rings closed, z absolute.
        "roofs": _roof_faces(prism, tile),
    }


def _roof_faces(prism: Prism, tile: TileId) -> list:
    """Roof faces as rings of [x, y, z]: x/y relative to the tile origin, z
    absolute, all in cm-rounded metres.

    Plain rounding is fine here (unlike the footprints): the horizon only
    uses the faces' edges, so a few mm of shift cannot create invalid input.
    """
    ox, oy = tile.origin
    return [
        [
            [
                [
                    round(x - ox, _METRE_DIGITS),
                    round(y - oy, _METRE_DIGITS),
                    round(z, _METRE_DIGITS),
                ]
                for x, y, z in ring
            ]
            for ring in face
        ]
        for face in prism.roof_faces
    ]


def analysis_tile(tile: TileId, prisms: Iterable[Prism]) -> dict[str, Any]:
    return {
        "format": ANALYSIS_FORMAT,
        "version": ANALYSIS_VERSION,
        "tile": tile.key,
        "crs": "EPSG:25832",
        "heightReference": "DHHN2016 (NHN)",
        "origin": list(tile.origin),
        "buildings": [r for p in prisms if (r := analysis_record(p, tile)) is not None],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


@contextmanager
def open_geojsonseq(path: Path) -> Iterator[Callable[[Iterable[dict[str, Any]]], None]]:
    """Newline-delimited GeoJSON, which tippecanoe can read in parallel (-P).

    Yields a function that appends features, so callers can stream tiles in
    as they are parsed instead of holding a whole city in memory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:

        def write(features: Iterable[dict[str, Any]]) -> None:
            for f in features:
                out.write(json.dumps(f, ensure_ascii=False, separators=(",", ":")))
                out.write("\n")

        yield write
