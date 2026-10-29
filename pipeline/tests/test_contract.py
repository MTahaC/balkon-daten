"""The pipeline side of the data contract (docs/data-contract.md).

1. The pipeline's constants match contract/constants.json.
2. The pipeline reproduces the golden release in contract/fixtures/ byte for
   byte (except generatedAt). The app's tests parse the same files, so a
   format change on either side breaks a test.

After an intended format change: UPDATE_CONTRACT=1 pytest tests/test_contract.py
"""

import gzip
import inspect
import io
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

import lod2pipe.__main__ as cli
from lod2pipe import addresses, export, pack
from lod2pipe.chunks import DEFAULT_SIZE, chunk_dir, chunk_name, chunk_release
from lod2pipe.fetch import IndexEntry
from lod2pipe.tiles import TILE_SIZE_M, TileId, with_neighbours
from pvgisgrid import grid

REPO = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((REPO / "contract" / "constants.json").read_text(encoding="utf-8"))
GOLDEN = REPO / "contract" / "fixtures"
FIXTURE_GML = Path(__file__).parent / "fixtures" / "mini_tile.gml"
TILE = TileId(356, 5644)
GENERATED_AT = "2026-01-01T00:00:00+00:00"
# Gebäudereferenzen records inside the fixture tile (field layout as in the
# real file, see lod2pipe/addresses.py).
GEBREF_LINES = [
    "N;DENW37HK1000aaaA;A;05;Nordrhein-Westfalen;3;Köln;15;Köln;000;Köln;0000;;"
    "01234;Heumarkt;1;;32;356015.0;5644015.0;2026-07-01",
    "N;DENW37HK1000aaaB;A;05;Nordrhein-Westfalen;3;Köln;15;Köln;000;Köln;0000;;"
    "01234;Heumarkt;1;a;32;356030.0;5644015.0;2026-07-01",
    "N;DENW37HK1000aaaC;A;05;Nordrhein-Westfalen;3;Köln;15;Köln;000;Köln;0000;;"
    "05678;Gürzenichstr.;2;;32;356040.0;5644040.0;2026-07-01",
]
# Stand-in for buildings.pmtiles: the contract test is about piece naming
# and lengths, not tile content. Small pieces keep the fixture tiny.
DUMMY_ARCHIVE = bytes(i % 251 for i in range(2500))
FIXTURE_PIECE_SIZE = 1024


def test_constants_match_the_contract():
    assert TILE_SIZE_M == CONTRACT["tileSizeM"]
    assert export.ANALYSIS_FORMAT == CONTRACT["analysisFormat"]
    assert export.ANALYSIS_VERSION == CONTRACT["analysisVersion"]
    assert pack.PACKED_VERSION == CONTRACT["analysisPackedVersion"]
    assert pack.PIECE_SIZE == CONTRACT["analysisPieceSize"]
    assert pack.INDEX_NAME == CONTRACT["analysisIndex"]
    assert addresses.FORMAT == CONTRACT["addressFormat"]
    assert addresses.VERSION == CONTRACT["addressVersion"]
    assert cli.LAYER == CONTRACT["displayLayer"]
    assert DEFAULT_SIZE == CONTRACT["pieceSize"]
    example = CONTRACT["pieceExample"]
    piece = chunk_dir(Path(example["archive"])) / chunk_name(example["index"])
    assert piece.as_posix() == example["path"]
    assert float(grid.BASE_PARAMS["loss"]) / 100 == CONTRACT["systemLoss"]
    rings = inspect.signature(with_neighbours).parameters["rings"].default
    assert rings == CONTRACT["neighbourRings"]
    # One ring of neighbours must cover the app's shading radius plus margin.
    assert rings * TILE_SIZE_M >= CONTRACT["horizonRadiusM"] + CONTRACT["tileMarginM"]


def build_release(out: Path, work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Run the CLI on the fixture tile with network and external tools stubbed."""
    cache = work / "cache"
    cache.mkdir(parents=True)
    shutil.copy(FIXTURE_GML, cache / TILE.file_name)
    size = (cache / TILE.file_name).stat().st_size
    monkeypatch.setattr(
        cli, "load_index", lambda _c: {TILE.file_name: IndexEntry(size, "2026-07-01T00:00:00")}
    )
    gebref = work / "gebref.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("gebref.txt", "\n".join(GEBREF_LINES) + "\n")
    gebref.write_bytes(buf.getvalue())
    monkeypatch.setattr(addresses, "fetch_gebref", lambda _c: gebref)
    monkeypatch.setattr(
        cli, "_run_tippecanoe", lambda _g, target, _a: target.write_bytes(DUMMY_ARCHIVE)
    )
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)  # no `pmtiles verify`
    tiles_txt = work / "tiles.txt"
    tiles_txt.write_text(f"{TILE.key}\n", encoding="utf-8")
    cli.main(
        [
            "--tiles", str(tiles_txt), "--cache", str(cache), "--out", str(out),
            "--work", str(work / "w"), "--jobs", "1", "--release", "contract",
            "--skip-basemap",
        ]
    )  # fmt: skip
    chunk_release(out, FIXTURE_PIECE_SIZE)
    pack.pack_release(out)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["generatedAt"] = GENERATED_AT
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def files(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def packed_tiles(root: Path) -> dict[str, dict]:
    """The v3 tiles of a release, decoded (independent of the gzip bytes)."""
    index = json.loads((root / pack.INDEX_NAME).read_text(encoding="utf-8"))
    out = {}
    for key, (p, offset, length) in index["tiles"].items():
        data = (root / pack.PIECE_DIR / index["pieces"][p]).read_bytes()
        out[key] = pack.decode_tile(gzip.decompress(data[offset : offset + length]))
    return out


def is_packed(name: str) -> bool:
    return name == pack.INDEX_NAME or name.startswith(pack.PIECE_DIR + "/")


def test_pipeline_reproduces_the_golden_release(tmp_path, monkeypatch):
    out = tmp_path / "release"
    build_release(out, tmp_path / "work", monkeypatch)
    if os.environ.get("UPDATE_CONTRACT") == "1":
        shutil.rmtree(GOLDEN, ignore_errors=True)
        shutil.copytree(out, GOLDEN)
    built, golden = files(out), files(GOLDEN)
    # The golden files come from Linux, where releases are built (CI uploads
    # regenerated ones as an artifact when this test fails). Other systems'
    # zlib compresses the v3 pieces to different bytes, so there the packed
    # files are compared by content instead.
    exact = sys.platform == "linux"
    if not exact:
        assert packed_tiles(out) == packed_tiles(GOLDEN), "packed analysis tiles changed"
        built = {k: v for k, v in built.items() if not is_packed(k)}
        golden = {k: v for k, v in golden.items() if not is_packed(k)}
    assert sorted(built) == sorted(golden), (
        "file list changed (UPDATE_CONTRACT=1 after a deliberate change)"
    )
    for name, data in built.items():
        assert data == golden[name], f"{name} changed (UPDATE_CONTRACT=1 after a deliberate change)"
