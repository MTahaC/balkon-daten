import pytest

from lod2pipe.tiles import TileId, read_tile_list, tiles_in_bbox, with_neighbours


def test_parse_key_and_file_name():
    assert TileId.parse("356_5644") == TileId(356, 5644)
    assert TileId.parse("LoD2_32_356_5644_1_NW.gml") == TileId(356, 5644)
    with pytest.raises(ValueError):
        TileId.parse("LoD2_32_356_5644_2_NW.gml")


def test_names_and_bounds():
    t = TileId(356, 5644)
    assert t.key == "356_5644"
    assert t.file_name == "LoD2_32_356_5644_1_NW.gml"
    assert t.url.endswith("/lod2_gml/lod2_gml/LoD2_32_356_5644_1_NW.gml")
    assert t.bounds == (356000, 5644000, 357000, 5645000)


def test_containing_point():
    # Cologne reference point, projected to EPSG:25832.
    assert TileId.containing(356159.0, 5644748.0) == TileId(356, 5644)
    # A point exactly on a tile corner belongs to the tile north-east of it.
    assert TileId.containing(356000.0, 5644000.0) == TileId(356, 5644)


def test_tiles_in_bbox_is_half_open():
    assert tiles_in_bbox(356000, 5644000, 357000, 5645000) == [TileId(356, 5644)]
    assert tiles_in_bbox(355500, 5644200, 356100, 5644300) == [TileId(355, 5644), TileId(356, 5644)]
    with pytest.raises(ValueError):
        tiles_in_bbox(1, 1, 1, 2)


def test_read_tile_list_ignores_comments_and_duplicates():
    text = "# header\n356_5644  # Köln\n\n355_5644\n356_5644\n"
    assert read_tile_list(text) == [TileId(355, 5644), TileId(356, 5644)]


def test_with_neighbours_adds_one_ring_once():
    ring = with_neighbours([TileId(356, 5644), TileId(357, 5644)])
    assert len(ring) == 4 * 3  # 4 columns x 3 rows, the shared ones once
    assert ring[0] == TileId(355, 5643) and ring[-1] == TileId(358, 5645)
    assert with_neighbours([TileId(356, 5644)], rings=0) == [TileId(356, 5644)]
