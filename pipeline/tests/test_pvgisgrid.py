import io
import urllib.error

import pytest

from pvgisgrid.grid import (
    AZIMUTHS,
    LATS,
    LONS,
    TILTS,
    build_grid,
    fetch_with_retry,
    parse_pvcalc,
    pvcalc_url,
    to_pvgis_aspect,
)


def _response(e_y: float) -> dict:
    """Shape of a PVcalc v5_3 JSON response (only the fields we read)."""
    return {
        "outputs": {
            "totals": {"fixed": {"E_y": e_y}},
            "monthly": {"fixed": [{"month": m, "E_m": e_y / 12} for m in range(12, 0, -1)]},
        }
    }


@pytest.mark.parametrize(
    ("azimuth", "aspect"),
    [(180, 0), (90, -90), (270, 90), (0, 180), (135, -45), (225, 45), (315, 135), (45, -135)],
)
def test_azimuth_to_pvgis_aspect(azimuth, aspect):
    assert to_pvgis_aspect(azimuth) == aspect


def test_grid_covers_nrw_with_margin():
    # NRW: 50.32–52.53 °N, 5.87–9.46 °E; interpolation needs a node beyond.
    assert LATS[0] < 50.32 and LATS[-1] >= 52.5
    assert LONS[0] < 5.87 and LONS[-1] > 9.46


def test_url_uses_shared_parameters():
    url = pvcalc_url(50.94, 6.96, 180, 90)
    for part in ("lat=50.94", "lon=6.96", "angle=90", "aspect=0", "loss=14", "usehorizon=0"):
        assert part in url
    assert url.startswith("https://re.jrc.ec.europa.eu/api/v5_3/PVcalc?")


def test_parse_sorts_months():
    r = parse_pvcalc(_response(1200))
    assert r.annual_kwh_per_kwp == 1200
    assert r.monthly_kwh_per_kwp == [100.0] * 12


def test_retry_backs_off_on_429_then_succeeds():
    calls, sleeps = [], []

    def opener(url):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, io.BytesIO())
        return _response(1)

    assert fetch_with_retry("u", opener, sleep=sleeps.append) == _response(1)
    assert sleeps == [2.0, 4.0]


def test_retry_does_not_retry_client_errors():
    def opener(url):
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, io.BytesIO())

    with pytest.raises(urllib.error.HTTPError):
        fetch_with_retry("u", opener, sleep=lambda s: None)


def test_build_grid_shape_and_order():
    seen = []

    def opener(url):
        seen.append(url)
        return _response(len(seen))  # value encodes the request order

    grid = build_grid(opener=opener, pause_s=0, sleep=lambda s: None)
    assert len(seen) == len(LATS) * len(LONS) * len(AZIMUTHS) * len(TILTS)
    a = grid["annual"]
    assert (len(a), len(a[0]), len(a[0][0]), len(a[0][0][0])) == (
        len(LATS),
        len(LONS),
        len(AZIMUTHS),
        len(TILTS),
    )
    # Innermost loop is tilt, then azimuth, lon, lat.
    assert a[0][0][0] == [1.0, 2.0, 3.0]
    assert a[0][0][1][0] == 4.0
    assert len(grid["monthly"][0][0][0][0]) == 12
    assert grid["attribution"].startswith("PVGIS ©")
