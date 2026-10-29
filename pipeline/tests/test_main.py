"""End-to-end run of the CLI on the fixture tile, without network or tippecanoe."""

import json
import shutil
from pathlib import Path

import lod2pipe.__main__ as cli
from lod2pipe.fetch import IndexEntry
from lod2pipe.tiles import TileId

FIXTURE = Path(__file__).parent / "fixtures" / "mini_tile.gml"
TILE = TileId(356, 5644)


def test_main_writes_manifest_analysis_and_display_features(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    # The tile is already cached with the size the (stubbed) portal index
    # reports, so fetch_tile doesn't download anything.
    shutil.copy(FIXTURE, cache / TILE.file_name)
    size = (cache / TILE.file_name).stat().st_size
    index = {TILE.file_name: IndexEntry(size, "2026-07-01T00:00:00")}
    monkeypatch.setattr(cli, "load_index", lambda _cache: index)
    tiles_txt = tmp_path / "tiles.txt"
    tiles_txt.write_text(f"{TILE.key}\n", encoding="utf-8")
    out, work = tmp_path / "out", tmp_path / "work"

    cli.main(
        [
            "--tiles", str(tiles_txt),
            "--cache", str(cache),
            "--out", str(out),
            "--work", str(work),
            "--jobs", "1",
            "--release", "r1",
            "--skip-tiles", "--skip-basemap", "--skip-addresses",
        ]
    )  # fmt: skip

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["release"] == "r1"
    assert manifest["tiles"] == [TILE.key]
    assert manifest["analysisPath"] == "analysis/{tile}.json"
    assert manifest["pmtiles"] is None and manifest["basemap"] is None
    assert "Land NRW (2026)" in manifest["attribution"]

    analysis = json.loads((out / "analysis" / f"{TILE.key}.json").read_text(encoding="utf-8"))
    assert analysis["format"] == "balkon-lod2-prisms" and analysis["tile"] == TILE.key
    assert len(analysis["buildings"]) > 0

    lines = (work / "buildings.geojsonl").read_text(encoding="utf-8").splitlines()
    ids = [json.loads(line)["properties"]["id"] for line in lines]
    assert sorted(ids) == sorted(b["id"] for b in analysis["buildings"])
    # The cached CityGML stays unless --delete-downloads is given.
    assert (cache / TILE.file_name).exists()
