from pathlib import Path

import pytest

from lod2pipe.citygml import ParseStats, parse_prisms

FIXTURE = Path(__file__).parent / "fixtures" / "mini_tile.gml"


@pytest.fixture(scope="module")
def parsed():
    stats = ParseStats()
    prisms = {p.id: p for p in parse_prisms(FIXTURE, stats)}
    return prisms, stats


def test_one_prism_per_building_or_part(parsed):
    prisms, stats = parsed
    assert set(prisms) == {
        "B_FLAT",
        "B_GABLE",
        "B_PARTS_NAVE",
        "B_PARTS_TOWER",
        "B_COURT",
        "B_NOGROUND",
    }
    assert stats.buildings == 5
    assert stats.prisms == 6


def test_flat_roof_box(parsed):
    p = parsed[0]["B_FLAT"]
    assert p.footprint.area == pytest.approx(100)
    assert (p.ground_z, p.eave_z, p.ridge_z) == (50, 62, 62)
    assert p.height == pytest.approx(12)
    assert p.measured_height == 12
    assert p.roof_type == "1000"
    assert p.function == "31001_1000"


def test_gable_roof_keeps_eave_and_ridge(parsed):
    p = parsed[0]["B_GABLE"]
    assert p.eave_height == pytest.approx(6)
    assert p.height == pytest.approx(10)
    assert p.footprint.area == pytest.approx(80)


def test_building_parts_keep_their_own_height(parsed):
    prisms = parsed[0]
    nave, tower = prisms["B_PARTS_NAVE"], prisms["B_PARTS_TOWER"]
    assert nave.building_id == tower.building_id == "B_PARTS"
    assert nave.height == pytest.approx(15)
    assert tower.height == pytest.approx(40)
    assert tower.footprint.area == pytest.approx(25)
    assert tower.function == "31001_3040"  # inherited from the building


def test_courtyard_is_a_hole(parsed):
    p = parsed[0]["B_COURT"]
    assert p.footprint.area == pytest.approx(30 * 30 - 10 * 10)
    assert len(p.footprint.interiors) == 1
    assert p.measured_height is None


def test_exterior_rings_are_counter_clockwise(parsed):
    # Source ground rings are clockwise; GeoJSON wants CCW exteriors.
    for p in parsed[0].values():
        polys = getattr(p.footprint, "geoms", [p.footprint])
        assert all(poly.exterior.is_ccw for poly in polys), p.id


def test_footprint_from_roof_when_ground_missing(parsed):
    prisms, stats = parsed
    p = prisms["B_NOGROUND"]
    assert stats.footprint_from_roof == 1
    assert p.footprint.area == pytest.approx(36)
    assert p.ground_z == 51  # lowest wall vertex
    assert p.height == pytest.approx(7)


def test_rejects_unexpected_crs(tmp_path):
    other = tmp_path / "other.gml"
    other.write_text(
        FIXTURE.read_text(encoding="utf-8").replace(
            "urn:adv:crs:ETRS89_UTM32*DE_DHHN2016_NH", "EPSG:4326"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="srsName"):
        list(parse_prisms(other))


def test_roof_faces_are_kept_in_3d(parsed):
    gable = parsed[0]["B_GABLE"]
    assert len(gable.roof_faces) == 2
    zs = {z for face in gable.roof_faces for ring in face for _, _, z in ring}
    assert zs == {56, 60}
    court = parsed[0]["B_COURT"]
    assert len(court.roof_faces[0]) == 2  # exterior + courtyard ring
