"""Download LoD2 tiles from opengeodata.nrw.de into a local cache."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .tiles import INDEX_URL, TileId

_USER_AGENT = "balkon-ertrag-check-pipeline/0.1"
_TIMEOUT_S = 120


def _open(url: str):
    # Only called with our fixed https:// portal URLs.
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    return urllib.request.urlopen(req, timeout=_TIMEOUT_S)  # noqa: S310


@dataclass(frozen=True)
class IndexEntry:
    size: int
    timestamp: str  # ISO 8601, as published by the portal


def parse_index(data: dict) -> dict[str, IndexEntry]:
    files = data["datasets"][0]["files"]
    return {f["name"]: IndexEntry(int(f["size"]), f["timestamp"]) for f in files}


def load_index(cache_dir: Path) -> dict[str, IndexEntry]:
    """File name -> size and timestamp, from the portal's ``index.json``.

    The index is re-downloaded on every run (it is ~3 MB) so that we notice
    updated tiles via changed file sizes.
    """
    with _open(INDEX_URL) as resp:
        data = json.load(resp)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "index.json").write_text(json.dumps(data), encoding="utf-8")
    return parse_index(data)


def _download(url: str, target: Path, expected_size: int, opener: Callable = _open) -> None:
    partial = target.with_suffix(".part")
    with opener(url) as resp, partial.open("wb") as out:
        shutil.copyfileobj(resp, out, length=1 << 20)
    size = partial.stat().st_size
    if size != expected_size:
        partial.unlink()
        raise OSError(f"{target.name}: got {size} bytes, index says {expected_size}")
    partial.replace(target)


def fetch_tile(
    tile: TileId,
    cache_dir: Path,
    expected_size: int,
    opener: Callable = _open,
    retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> Path:
    """Return the local path of a tile, downloading it if missing or stale.

    The portal occasionally resets connections (seen once in 115 downloads
    while building Köln), so network errors, HTTP 429/5xx and truncated
    downloads are retried with exponential backoff (2, 4, 8, 16, 32 s).
    """
    target = cache_dir / tile.file_name
    if target.exists() and target.stat().st_size == expected_size:
        return target
    cache_dir.mkdir(parents=True, exist_ok=True)
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            _download(tile.url, target, expected_size, opener)
            return target
        except urllib.error.HTTPError as e:
            if not (e.code == 429 or e.code >= 500) or attempt == retries:
                raise
        except OSError:  # URLError, connection reset, timeout, truncated file
            if attempt == retries:
                raise
        print(f"{tile.key}: download failed, retrying in {delay:.0f} s", flush=True)
        sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")
