import io
import urllib.error

import pytest

from lod2pipe.fetch import fetch_tile
from lod2pipe.tiles import TileId

TILE = TileId(356, 5644)


def opener_with(results):
    """Each call returns the next payload or raises the next exception."""
    calls = []

    def opener(url):
        calls.append(url)
        r = results[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return io.BytesIO(r)

    return opener, calls


def test_retries_resets_and_truncated_downloads(tmp_path):
    opener, calls = opener_with(
        [ConnectionResetError(104, "reset"), b"short", urllib.error.URLError("reset"), b"x" * 10]
    )
    sleeps = []
    path = fetch_tile(TILE, tmp_path, 10, opener=opener, sleep=sleeps.append)
    assert path.read_bytes() == b"x" * 10
    assert len(calls) == 4 and sleeps == [2.0, 4.0, 8.0]
    assert not path.with_suffix(".part").exists()


def test_cached_tile_is_not_downloaded(tmp_path):
    (tmp_path / TILE.file_name).write_bytes(b"y" * 10)
    opener, calls = opener_with([])
    fetch_tile(TILE, tmp_path, 10, opener=opener)
    assert calls == []


def test_gives_up_on_404_and_after_the_last_retry(tmp_path):
    not_found = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    opener, calls = opener_with([not_found])
    with pytest.raises(urllib.error.HTTPError):
        fetch_tile(TILE, tmp_path, 10, opener=opener, sleep=lambda s: None)
    assert len(calls) == 1

    opener, calls = opener_with([ConnectionResetError()] * 3)
    with pytest.raises(ConnectionResetError):
        fetch_tile(TILE, tmp_path, 10, opener=opener, retries=2, sleep=lambda s: None)
    assert len(calls) == 3
