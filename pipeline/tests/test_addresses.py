import io
import zipfile

import pytest
from pyproj import Transformer
from shapely.geometry import Point, shape

from lod2pipe.addresses import (
    Address,
    build_index,
    display_street,
    in_tiles,
    municipality_tiles,
    parse_line,
    read_gebref,
)
from lod2pipe.basemap import MAX_ZOOM, extract_command, extract_region
from lod2pipe.tiles import TileId

# Real records from the 2026-07 Gebäudereferenzen (Köln), plus edge cases.
LINE = (
    "N;DENW37HK1000ea0D;A;05;Nordrhein-Westfalen;3;Köln;15;Köln;000;Köln;0000;;"
    "01129;Gilbachstr.;15;;32;355165.793;5645803.098;2026-07-01"
)
LINE_SUFFIX = (
    "N;DENW01HK10000a4O;B;05;Nordrhein-Westfalen;9;Arnsberg;11;Bochum;000;Bochum;0000;;"
    "04176;Wilhelm-Leithe-Weg;76;a;32;370473.340;5703695.059;2026-07-01"
)
TILES = [TileId(355, 5644), TileId(356, 5644)]


def test_display_street_expands_str_only():
    assert display_street("Gilbachstr.") == "Gilbachstraße"
    assert display_street("Aachener Str.") == "Aachener Straße"
    assert display_street("Adolf-Fischer-Str.") == "Adolf-Fischer-Straße"
    assert display_street("An Groß St.Martin") == "An Groß St.Martin"
    assert display_street("Dr.-Simons-Str.") == "Dr.-Simons-Straße"
    assert display_street("Heumarkt") == "Heumarkt"


def test_parse_line():
    a = parse_line(LINE)
    assert a == Address("Köln", "Gilbachstraße", "15", "", 355165.793, 5645803.098)
    b = parse_line(LINE_SUFFIX + "\r\n")
    assert b is not None and (b.number, b.suffix) == ("76", "a")


def test_parse_line_rejects_broken_records():
    assert parse_line("") is None
    assert parse_line(LINE.replace(";15;;32;", ";;;32;")) is None  # no house number
    assert parse_line(LINE.replace("355165.793", "x")) is None


def test_in_tiles_keeps_only_processed_tiles():
    inside = Address("Köln", "A", "1", "", 356500.0, 5644500.0)
    north = Address("Köln", "B", "1", "", 356500.0, 5645500.0)
    assert list(in_tiles([inside, north], TILES)) == [inside]


def test_build_index_groups_sorts_and_offsets():
    addrs = [
        Address("Köln", "Heumarkt", "10", "", 356600.04, 5644500.0),
        Address("Köln", "Heumarkt", "2", "a", 356610.0, 5644510.0),
        Address("Köln", "Heumarkt", "2", "", 356620.0, 5644520.0),
        Address("Köln", "Alter Markt", "1", "", 356700.0, 5644700.0),
    ]
    idx = build_index(addrs, TILES)
    assert idx["format"] == "balkon-addresses" and idx["version"] == 1
    assert idx["origin"] == [355000, 5644000]
    assert [s[0] for s in idx["streets"]] == ["Alter Markt", "Heumarkt"]
    heumarkt = idx["streets"][1]
    assert heumarkt[1] == "Köln"
    # numeric order, suffixes after the plain number
    assert [(n[0], n[1]) for n in heumarkt[2]] == [("2", ""), ("2", "a"), ("10", "")]
    assert heumarkt[2][2][2:] == [1600.0, 500.0]


def test_read_gebref_from_zip(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("gebref.txt", f"{LINE}\n\n{LINE_SUFFIX}\n")
    path = tmp_path / "g.zip"
    path.write_bytes(buf.getvalue())
    assert [a.street for a in read_gebref(path)] == ["Gilbachstraße", "Wilhelm-Leithe-Weg"]


def test_municipality_tiles_and_suggestions():
    addrs = [
        Address("Köln", "A", "1", "", 356500.0, 5644500.0),
        Address("Köln", "B", "2", "", 356900.0, 5644100.0),
        Address("Köln", "C", "3", "", 355100.0, 5645900.0),
        Address("Leverkusen", "D", "4", "", 362500.0, 5655500.0),
    ]
    assert municipality_tiles(addrs, "Köln") == [TileId(355, 5645), TileId(356, 5644)]
    with pytest.raises(ValueError, match="did you mean Köln"):
        municipality_tiles(addrs, "Koln")


def test_basemap_region_follows_tiles_plus_margin():
    # An L of three tiles: the region must not fill the empty corner.
    tiles = [TileId(355, 5644), TileId(356, 5644), TileId(355, 5645)]
    region = shape(extract_region(tiles, margin_m=500))
    assert region.geom_type == "Polygon"
    to_wgs84 = Transformer.from_crs("EPSG:25832", "EPSG:4326", always_xy=True).transform
    inside = [(355000 - 400, 5644000 - 400), (357000 + 400, 5645000 - 10), (356000 - 10, 5646400)]
    for x, y in inside:
        assert region.contains(Point(to_wgs84(x, y))), (x, y)
    # Centre of the missing NE tile, 500 m beyond any data tile.
    assert not region.contains(Point(to_wgs84(356800, 5645800)))
    assert not region.contains(Point(to_wgs84(357000 + 700, 5644500)))


def test_basemap_command_pins_build_and_zoom(tmp_path):
    cmd = extract_command("pmtiles", tmp_path / "r.geojson", tmp_path / "b.pmtiles")
    assert cmd[1] == "extract"
    assert cmd[2].startswith("https://build.protomaps.com/") and cmd[2].endswith(".pmtiles")
    assert f"--region={tmp_path / 'r.geojson'}" in cmd
    assert f"--maxzoom={MAX_ZOOM}" in cmd
