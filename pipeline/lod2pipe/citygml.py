"""Stream-parse NRW LoD2 CityGML 1.0 into simplified building prisms.

Why prisms? For shading at balcony scale we only need "how high does an
obstacle reach above which ground area". A prism (2D footprint extruded
between ground and roof height) captures that with a tiny fraction of the
data. We keep two roof heights per prism:

* ``eave_z`` - lowest roof vertex (gutter line for pitched roofs)
* ``ridge_z`` - highest roof vertex

Using only the ridge would overestimate shading by pitched roofs (a gable
roof is a wedge, not a block); using only the eave would underestimate it.
For shading we therefore also keep the roof surfaces themselves
(``roof_faces``): the highest point of a building along any line of sight
lies on a roof edge, so the roof polygons are all the horizon needs.

We emit one prism per ``bldg:BuildingPart`` (or per ``bldg:Building`` when it
has no parts). Parts exist exactly where heights differ within one building,
e.g. a church tower on a nave, so merging them would turn the tower into a
solid block of tower height.

All coordinates stay in the source CRS: ETRS89 / UTM32N (EPSG:25832) in
metres, heights in DHHN2016 (normal heights above sea level, "NHN").
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from lxml import etree
from shapely import MultiPolygon, Polygon, make_valid, unary_union
from shapely.geometry.base import BaseGeometry
from shapely.geometry.polygon import orient

CORE = "http://www.opengis.net/citygml/1.0"
BLDG = "http://www.opengis.net/citygml/building/1.0"
GML = "http://www.opengis.net/gml"
NS = {"core": CORE, "bldg": BLDG, "gml": GML}

# The NRW files declare this compound CRS: EPSG:25832 + DHHN2016 heights.
EXPECTED_SRS = "urn:adv:crs:ETRS89_UTM32*DE_DHHN2016_NH"

_BUILDING = f"{{{BLDG}}}Building"
_ENVELOPE = f"{{{GML}}}Envelope"
_GML_ID = f"{{{GML}}}id"

# Footprint slivers below this area (m²) are dropped after cleaning.
_MIN_AREA_M2 = 0.5

Ring = list[tuple[float, float, float]]


@dataclass(frozen=True)
class Prism:
    id: str
    building_id: str
    footprint: Polygon | MultiPolygon  # EPSG:25832, metres
    ground_z: float
    eave_z: float
    ridge_z: float
    measured_height: float | None
    roof_type: str | None
    # ALKIS/ATKIS function code, e.g. "31001_1000" (Wohnhaus). Codes starting
    # with 53001 (bridges) or 51009 (canopies, carports) are structures, not
    # buildings: they do not reach down to the ground as solid blocks.
    function: str | None
    # Roof polygons as 3D rings: each face is [exterior, *interiors], each
    # ring closed, EPSG:25832 metres with absolute DHHN2016 heights.
    roof_faces: list[list[Ring]]

    @property
    def height(self) -> float:
        """Ridge height above ground in metres."""
        return self.ridge_z - self.ground_z

    @property
    def eave_height(self) -> float:
        return self.eave_z - self.ground_z


@dataclass
class ParseStats:
    buildings: int = 0
    prisms: int = 0
    # Footprint taken from the roof projection because GroundSurface is missing.
    footprint_from_roof: int = 0
    skipped_no_roof: int = 0
    skipped_empty_footprint: int = 0


def _pos_list(el: etree._Element) -> Ring:
    """Parse a 3D ``gml:posList`` into (x, y, z) tuples."""
    if el.get("srsDimension", "3") != "3":
        raise ValueError("Only 3D posList is supported")
    values = [float(v) for v in el.text.split()]
    if len(values) % 3:
        raise ValueError("posList length is not a multiple of 3")
    return list(zip(values[0::3], values[1::3], values[2::3], strict=True))


def _polygons(surface: etree._Element) -> Iterator[tuple[Ring, list[Ring]]]:
    """Yield (exterior, interiors) rings of every gml:Polygon in a surface."""
    for poly in surface.iterfind(".//gml:Polygon", NS):
        ext = poly.find("gml:exterior//gml:posList", NS)
        if ext is None:
            raise ValueError("Polygon without exterior posList")
        holes = [_pos_list(p) for p in poly.iterfind("gml:interior//gml:posList", NS)]
        yield _pos_list(ext), holes


def _surfaces(el: etree._Element, kind: str) -> list[etree._Element]:
    # Only *direct* boundedBy children: surfaces of nested BuildingParts belong
    # to those parts, not to the parent building.
    return el.findall(f"bldg:boundedBy/bldg:{kind}", NS)


def _areal_parts(geom: BaseGeometry) -> list[Polygon]:
    """Polygons inside any geometry; make_valid/union may return collections
    that also contain (degenerate) lines and points, which we drop."""
    if isinstance(geom, Polygon):
        return [geom]
    return [p for g in getattr(geom, "geoms", []) for p in _areal_parts(g)]


def _footprint(polys: Iterable[tuple[Ring, list[Ring]]]) -> Polygon | MultiPolygon:
    """Union of 3D polygons projected onto the horizontal plane."""
    parts = []
    for ext, holes in polys:
        p = Polygon([(x, y) for x, y, _ in ext], [[(x, y) for x, y, _ in h] for h in holes])
        # Projected roof faces can be degenerate (vertical) or self-touching;
        # make_valid repairs them before the union.
        parts.append(make_valid(p))
    # Exterior rings counter-clockwise, as GeoJSON (RFC 7946) recommends.
    polygons = [
        orient(p, sign=1.0) for p in _areal_parts(unary_union(parts)) if p.area >= _MIN_AREA_M2
    ]
    if not polygons:
        return Polygon()
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def _float_child(el: etree._Element, path: str) -> float | None:
    text = el.findtext(path, namespaces=NS)
    return float(text) if text else None


def _prism(
    el: etree._Element, building_id: str, parent_function: str | None, stats: ParseStats
) -> Prism | None:
    roof_polys = [p for s in _surfaces(el, "RoofSurface") for p in _polygons(s)]
    if not roof_polys:
        # A Building that only aggregates BuildingParts has no own surfaces.
        return None
    ground_polys = [p for s in _surfaces(el, "GroundSurface") for p in _polygons(s)]

    roof_z = [z for ext, _ in roof_polys for _, _, z in ext]
    if ground_polys:
        footprint = _footprint(ground_polys)
        ground_z = min(z for ext, _ in ground_polys for _, _, z in ext)
    else:
        # LoD2 walls are vertical, so the roof's projection equals the footprint.
        stats.footprint_from_roof += 1
        footprint = _footprint(roof_polys)
        wall_z = [z for s in _surfaces(el, "WallSurface") for e, _ in _polygons(s) for *_, z in e]
        ground_z = min(wall_z) if wall_z else min(roof_z)

    if footprint.is_empty:
        stats.skipped_empty_footprint += 1
        return None

    return Prism(
        id=el.get(_GML_ID, building_id),
        building_id=building_id,
        footprint=footprint,
        ground_z=ground_z,
        eave_z=min(roof_z),
        ridge_z=max(roof_z),
        measured_height=_float_child(el, "bldg:measuredHeight"),
        roof_type=el.findtext("bldg:roofType", namespaces=NS),
        # BuildingParts usually inherit the function of their building.
        function=el.findtext("bldg:function", namespaces=NS) or parent_function,
        roof_faces=[[ext, *holes] for ext, holes in roof_polys],
    )


def _building_prisms(building: etree._Element, stats: ParseStats) -> Iterator[Prism]:
    bid = building.get(_GML_ID, "")
    function = building.findtext("bldg:function", namespaces=NS)
    parts = building.findall("bldg:consistsOfBuildingPart/bldg:BuildingPart", NS)
    for el in [building, *parts]:
        prism = _prism(el, bid, function, stats)
        if prism is not None:
            stats.prisms += 1
            yield prism
    if not parts and not _surfaces(building, "RoofSurface"):
        stats.skipped_no_roof += 1


def parse_prisms(path: Path, stats: ParseStats | None = None) -> Iterator[Prism]:
    """Stream all prisms of a CityGML file with constant memory.

    NRW tiles can be 80 MB, so we use ``iterparse`` and free each building
    after processing instead of building the full DOM.
    """
    stats = stats if stats is not None else ParseStats()
    srs_checked = False
    context = etree.iterparse(
        str(path),
        events=("end",),
        tag=(_ENVELOPE, _BUILDING),
        huge_tree=True,
        # The input is downloaded data: never resolve entities or fetch DTDs.
        resolve_entities=False,
        no_network=True,
    )
    for _, el in context:
        if el.tag == _ENVELOPE:
            if not srs_checked:
                srs = el.get("srsName")
                if srs != EXPECTED_SRS:
                    raise ValueError(f"{path.name}: unexpected srsName {srs!r}")
                srs_checked = True
            continue
        stats.buildings += 1
        yield from _building_prisms(el, stats)
        # Free memory: clear this building and drop already processed siblings.
        member = el.getparent()
        el.clear()
        if member is not None and (root := member.getparent()) is not None:
            while member.getprevious() is not None:
                del root[0]
    if not srs_checked:
        raise ValueError(f"{path.name}: no gml:Envelope with srsName found")
