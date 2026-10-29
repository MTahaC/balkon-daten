import json

import pytest
from test_pack import GABLE, ODD, read_tile, write_release

from lod2pipe import addresses, merge, pack
from lod2pipe.addresses import Address


def shard(path, keys, year="2026"):
    write_release(path, keys, [GABLE, ODD])
    manifest = json.loads((path / "manifest.json").read_text())
    manifest.update(
        {
            "bounds": [6.9, 50.9, 7.0, 51.0] if keys[0] < "357" else [7.0, 50.8, 7.1, 50.95],
            "attribution": f"LoD2 NRW: Land NRW ({year}), dl-de/zero",
            "coverage": "Nordrhein-Westfalen",
            "generatedAt": f"{year}-10-30T00:00:00+00:00",
        }
    )
    (path / "manifest.json").write_text(json.dumps(manifest))
    pack.pack_release(path)
    return path


def test_merge_keeps_every_tile_readable_and_lists_no_tiles(tmp_path):
    a = shard(tmp_path / "a", ["356_5644", "356_5645"])
    b = shard(tmp_path / "b", ["357_5644", "357_5645"], year="2025")
    out = tmp_path / "out"
    manifest = merge.merge_shards(out, [a, b])

    index = json.loads((out / pack.INDEX_NAME).read_text())
    assert sorted(index["tiles"]) == ["356_5644", "356_5645", "357_5644", "357_5645"]
    for key in index["tiles"]:
        assert read_tile(out, index, key)["tile"] == key
    assert manifest["tiles"] == [] and manifest["tilesFromIndex"] is True
    assert manifest["bounds"] == [6.9, 50.8, 7.1, 51.0]
    assert "(2026)" in manifest["attribution"]
    assert manifest["analysisIndex"] == pack.INDEX_NAME


def test_merge_refuses_a_tile_in_two_shards(tmp_path):
    a = shard(tmp_path / "a", ["356_5644"])
    b = shard(tmp_path / "b", ["356_5644"])
    with pytest.raises(ValueError, match="two shards"):
        merge.merge_shards(tmp_path / "out", [a, b])


def test_address_split_per_municipality(tmp_path):
    found = [
        Address("Köln", "Heumarkt", "10", "", 356600.0, 5644500.0),
        Address("Köln", "Gürzenichstraße", "2", "", 356550.0, 5644480.0),
        Address("Bonn", "Markt", "1", "", 365000.0, 5622000.0),
    ]
    streets = addresses.write_split(found, tmp_path)

    assert streets["format"] == addresses.STREETS_FORMAT
    assert json.loads((tmp_path / addresses.STREETS_NAME).read_text()) == streets
    towns = {t[0]: t for t in streets["municipalities"]}
    assert towns["Köln"][2] == [356550, 5644480, 356600, 5644500]
    assert towns["Köln"][3] == ["Gürzenichstraße", "Heumarkt"]
    numbers = json.loads((tmp_path / "addresses" / towns["Köln"][1]).read_text())
    assert numbers["format"] == addresses.FORMAT
    assert [s[0] for s in numbers["streets"]] == ["Gürzenichstraße", "Heumarkt"]
    assert towns["Bonn"][1] != towns["Köln"][1]
