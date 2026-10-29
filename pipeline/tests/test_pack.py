import gzip
import json

import pytest

from lod2pipe import pack


def tile(buildings, key="356_5644"):
    e, n = (int(v) for v in key.split("_"))
    return {
        "format": "balkon-lod2-prisms",
        "version": 2,
        "tile": key,
        "crs": "EPSG:25832",
        "heightReference": "DHHN2016 (NHN)",
        "origin": [e * 1000, n * 1000],
        "buildings": buildings,
    }


GABLE = {
    "id": "DENW37AL1000abcd",
    "groundZ": 49.77,
    "eaveZ": 53.68,
    "ridgeZ": 54.52,
    "function": "31001_2000",
    # Exterior ring and a hole, both closed.
    "polygons": [
        [
            [[0.0, 0.0], [10.5, 0.0], [10.5, 8.25], [0.0, 8.25], [0.0, 0.0]],
            [[2.0, 2.0], [2.0, 3.0], [3.0, 3.0], [2.0, 2.0]],
        ]
    ],
    "roofs": [
        [
            [
                [0.0, 0.0, 53.68],
                [10.5, 0.0, 53.68],
                [10.5, 4.12, 54.52],
                [0.0, 4.12, 54.52],
                [0.0, 0.0, 53.68],
            ]
        ],
        [[[0.0, 8.25, 53.68], [0.0, 4.12, 54.52], [10.5, 4.12, 54.52], [0.0, 8.25, 53.68]]],
    ],
}
# No function code, negative local coordinates (building over the tile
# edge), a ground below 0 m and an open ring.
ODD = {
    "id": "UUID_3dc48973-e2cf-403a-ac19-4a33e08d94f8",
    "groundZ": -1.5,
    "eaveZ": 3.0,
    "ridgeZ": 3.0,
    "function": None,
    "polygons": [[[[-4.31, 999.99], [-0.01, 1003.2], [-4.31, 1003.2], [-4.31, 999.99]]]],
    "roofs": [[[[-4.31, 999.99, 3.0], [-0.01, 1003.2, 3.0], [-4.31, 1003.2, 3.0]]]],
}


def roundtrip(t):
    return pack.decode_tile(pack.encode_tile(t))


def test_decoding_gives_v2_back_exactly():
    t = tile([GABLE, ODD])
    assert roundtrip(t) == {k: t[k] for k in ("tile", "origin", "buildings")}


def test_empty_tile():
    t = tile([])
    assert roundtrip(t)["buildings"] == []


def test_refuses_values_off_the_centimetre_grid():
    b = dict(GABLE, groundZ=49.775)
    with pytest.raises(ValueError, match="centimetre"):
        pack.encode_tile(tile([b]))


def test_refuses_an_origin_that_doesnt_match_the_key():
    t = tile([GABLE])
    t["origin"] = [356000, 5645000]
    with pytest.raises(ValueError, match="origin"):
        pack.encode_tile(t)


def test_binary_is_much_smaller_than_json():
    t = tile([GABLE, ODD] * 50)
    as_json = len(gzip.compress(json.dumps(t).encode()))
    assert len(pack.compress(pack.encode_tile(t))) < as_json * 0.8


def test_hilbert_neighbours_stay_close():
    # Inside an aligned 32 x 32 km block, consecutive positions on the curve
    # are always edge neighbours (E 320-351, N 5608-5639: offsets 608-639).
    cells = sorted(
        (pack.hilbert_index(e, n), (e, n)) for e in range(320, 352) for n in range(5608, 5640)
    )
    for (_, (e1, n1)), (_, (e2, n2)) in zip(cells, cells[1:], strict=False):
        assert abs(e1 - e2) + abs(n1 - n2) == 1


def write_release(root, keys, buildings):
    (root / "analysis").mkdir(parents=True)
    for key in keys:
        (root / "analysis" / f"{key}.json").write_text(json.dumps(tile(buildings, key)))
    (root / "manifest.json").write_text(json.dumps({"analysisPath": "analysis/{tile}.json"}))


def read_tile(root, index, key):
    p, offset, length = index["tiles"][key]
    data = (root / pack.PIECE_DIR / index["pieces"][p]).read_bytes()
    return pack.decode_tile(gzip.decompress(data[offset : offset + length]))


def test_pack_release_cuts_pieces_without_splitting_tiles(tmp_path):
    keys = [f"{e}_{n}" for e in range(356, 360) for n in range(5644, 5647)]
    write_release(tmp_path, keys, [GABLE, ODD] * 20)
    member = len(pack.compress(pack.encode_tile(tile([GABLE, ODD] * 20))))
    index = pack.pack_release(tmp_path, piece_size=member * 3 + 1)

    assert sorted(index["tiles"]) == sorted(keys)
    assert len(index["pieces"]) == 4  # 12 tiles, 3 per piece
    for key in keys:
        assert read_tile(tmp_path, index, key)["tile"] == key
    for name in index["pieces"]:
        assert (tmp_path / pack.PIECE_DIR / name).stat().st_size <= member * 3 + 1
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["analysisIndex"] == pack.INDEX_NAME
    assert json.loads((tmp_path / pack.INDEX_NAME).read_text()) == index


def test_a_tile_bigger_than_a_piece_gets_its_own(tmp_path):
    write_release(tmp_path, ["356_5644", "356_5645"], [GABLE] * 10)
    index = pack.pack_release(tmp_path, piece_size=10)
    assert len(index["pieces"]) == 2


def test_piece_names_depend_only_on_content(tmp_path):
    for name in ("a", "b"):
        write_release(tmp_path / name, ["356_5644", "357_5644"], [GABLE, ODD])
    first = pack.pack_release(tmp_path / "a")
    second = pack.pack_release(tmp_path / "b")
    assert first == second
    # Packing again replaces the old pieces instead of adding to them.
    pack.pack_release(tmp_path / "a")
    assert len(list((tmp_path / "a" / pack.PIECE_DIR).iterdir())) == len(first["pieces"])
