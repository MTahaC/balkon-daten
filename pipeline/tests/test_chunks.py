import json

from lod2pipe.chunks import chunk_dir, chunk_name, chunk_release


def test_chunk_release_splits_archives_and_records_them(tmp_path):
    data = bytes(range(256)) * 10  # 2560 bytes
    (tmp_path / "buildings.pmtiles").write_bytes(data)
    (tmp_path / "basemap.pmtiles").write_bytes(b"x" * 1000)
    (tmp_path / "manifest.json").write_text(json.dumps({"release": "r1"}), encoding="utf-8")

    chunks = chunk_release(tmp_path, size=1024)

    assert chunks == {
        "size": 1024,
        "archives": {"basemap.pmtiles": 1000, "buildings.pmtiles": 2560},
    }
    pieces = sorted(chunk_dir(tmp_path / "buildings.pmtiles").iterdir())
    assert [p.name for p in pieces] == [chunk_name(i) for i in range(3)]
    assert [p.stat().st_size for p in pieces] == [1024, 1024, 512]
    # Joining the pieces gives the archive back (the path back to R2).
    assert b"".join(p.read_bytes() for p in pieces) == data
    assert not (tmp_path / "buildings.pmtiles").exists()
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["release"] == "r1" and manifest["chunks"] == chunks


def test_chunk_release_can_keep_archives_and_reruns_cleanly(tmp_path):
    (tmp_path / "buildings.pmtiles").write_bytes(b"y" * 3000)
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    chunk_release(tmp_path, size=1024, keep=True)
    chunk_release(tmp_path, size=2048, keep=True)
    assert (tmp_path / "buildings.pmtiles").exists()
    names = sorted(p.name for p in chunk_dir(tmp_path / "buildings.pmtiles").iterdir())
    assert names == [chunk_name(0), chunk_name(1)]
