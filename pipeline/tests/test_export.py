import json

import pytest
from shapely import Polygon, box
from shapely.geometry import shape

from lod2pipe.citygml import Prism
from lod2pipe.export import (
    analysis_tile,
    display_feature,
    open_geojsonseq,
    snapped_polygons,
    to_wgs84,
)
from lod2pipe.tiles import TileId

TILE = TileId(356, 5644)


def _prism(footprint, **kw) -> Prism:
    defaults = dict(
        id="P1",
        building_id="B1",
        ground_z=50.004,
        eave_z=56.123,
        ridge_z=60.456,
        measured_height=10.45,
        roof_type="3100",
        function="31001_1000",
        roof_faces=[
            [
                [
                    (356010.0, 5644010.0, 56.123),
                    (356020.0, 5644010.0, 60.456),
                    (356010.0, 5644010.0, 56.123),
                ]
            ]
        ],
    )
    return Prism(footprint=footprint, **(defaults | kw))


def test_wgs84_reference_point():
    # On the central meridian (500 000 m easting) of UTM zone 32 the
    # longitude is exactly 9 degrees; northing 0 is the equator.
    p = to_wgs84(Polygon([(500000, 0), (500001, 0), (500000, 1)]))
    lon, lat = p.exterior.coords[0]
    assert lon == pytest.approx(9.0, abs=1e-9)
    assert lat == pytest.approx(0.0, abs=1e-9)


def test_wgs84_cologne_is_plausible():
    lon, lat = to_wgs84(box(356159, 5644748, 356160, 5644749)).exterior.coords[0]
    assert 6.9 < lon < 7.0
    assert 50.9 < lat < 51.0


def test_display_feature_properties_are_relative_heights():
    f = display_feature(_prism(box(356010, 5644010, 356020, 5644020)))
    assert f["geometry"]["type"] == "Polygon"
    assert f["properties"] == {
        "id": "P1",
        "h": 10.5,
        "h_eave": 6.1,
        "roof": "3100",
        "fn": "31001_1000",
        "area": 100,
    }
    lon = f["geometry"]["coordinates"][0][0][0]
    assert len(str(lon).split(".")[1]) <= 7


def test_analysis_tile_is_metric_and_relative_to_origin():
    footprint = Polygon(
        [(356010.004, 5644010), (356020, 5644010), (356020, 5644020), (356010, 5644020)]
    )
    data = analysis_tile(TILE, [_prism(footprint)])
    assert data["origin"] == [356000, 5644000]
    assert data["crs"] == "EPSG:25832"
    b = data["buildings"][0]
    assert (b["groundZ"], b["eaveZ"], b["ridgeZ"]) == (50.0, 56.12, 60.46)
    ring = b["polygons"][0][0]
    assert [10.0, 10.0] in ring  # 10.004 rounded to cm, relative to origin
    assert ring[0] == ring[-1]  # closed ring
    assert json.dumps(data)  # serialisable


def test_geojsonseq_one_feature_per_line(tmp_path):
    path = tmp_path / "x.geojsonl"
    feats = [
        display_feature(_prism(box(356010, 5644010, 356020, 5644020), id=str(i))) for i in range(3)
    ]
    with open_geojsonseq(path) as write:
        write(feats[:2])
        write(iter(feats[2:]))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["properties"]["id"] for line in lines] == ["0", "1", "2"]


def test_snapping_keeps_polygons_valid():
    # A courtyard 4 mm from the outer wall: naive rounding to cm would make
    # the hole touch the shell along an edge (invalid).
    hole = [(1, 0.004), (2, 0.004), (2, 1), (1, 1)]
    poly = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [hole])
    naive = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], [[(x, round(y, 2)) for x, y in hole]])
    assert not naive.is_valid

    snapped = shape({"type": "MultiPolygon", "coordinates": snapped_polygons(poly, 2)})
    assert snapped.is_valid
    assert snapped.area == pytest.approx(99, abs=0.01)


def test_analysis_tile_v2_has_relative_roof_faces_with_absolute_z():
    data = analysis_tile(TILE, [_prism(box(356010, 5644010, 356020, 5644020))])
    assert data["version"] == 2
    ring = data["buildings"][0]["roofs"][0][0]
    assert ring[0] == [10.0, 10.0, 56.12]
    assert ring[1] == [20.0, 10.0, 60.46]
