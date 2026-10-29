"""PVGIS grid definition, API access and output format.

Verified against the live API (2026-10-25): PVcalc v5_3, radiation database
PVGIS-SARAH3 (2005–2023), `aspect` 0 = south, 90 = west, -90 = east, no CORS
header (browser access blocked), rate limit 30 requests/s per IP.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

PVCALC_URL = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
ATTRIBUTION = "PVGIS © European Communities, 2001-2026"

# 0.5° grid with one step of margin around NRW (50.32–52.53 °N,
# 5.87–9.46 °E) so bilinear interpolation works up to the border.
LATS = [50.0, 50.5, 51.0, 51.5, 52.0, 52.5]
LONS = [5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5]
# Module azimuth in the app's convention: degrees clockwise from north.
AZIMUTHS = [0, 45, 90, 135, 180, 225, 270, 315]
# Railing-mounted (90°), angled (60°) and propped-up (30°) modules.
TILTS = [30, 60, 90]

# PVGIS parameters shared by all requests. 14 % system loss matches the
# app's model; usehorizon=0 because the app models buildings, not terrain.
BASE_PARAMS = {
    "peakpower": "1",
    "loss": "14",
    "usehorizon": "0",
    "pvtechchoice": "crystSi",
    "mountingplace": "free",
    "outputformat": "json",
}

_USER_AGENT = "balkon-ertrag-check-pipeline/0.1"


def to_pvgis_aspect(azimuth: float) -> float:
    """App azimuth (0 = N, 90 = E, clockwise) -> PVGIS aspect (0 = S, -90 = E).

    PVGIS measures from south with east negative, so aspect = azimuth - 180,
    wrapped into (-180, 180]. North-facing (azimuth 0) becomes 180.
    """
    aspect = (azimuth - 180) % 360
    return aspect - 360 if aspect > 180 else aspect


@dataclass(frozen=True)
class Result:
    annual_kwh_per_kwp: float
    monthly_kwh_per_kwp: list[float]


def parse_pvcalc(data: dict[str, Any]) -> Result:
    fixed = data["outputs"]["totals"]["fixed"]
    months = sorted(data["outputs"]["monthly"]["fixed"], key=lambda m: m["month"])
    if len(months) != 12:
        raise ValueError("PVGIS response without 12 months")
    return Result(float(fixed["E_y"]), [float(m["E_m"]) for m in months])


def pvcalc_url(lat: float, lon: float, azimuth: float, tilt: float) -> str:
    params = dict(BASE_PARAMS)
    params.update(lat=f"{lat}", lon=f"{lon}", angle=f"{tilt}", aspect=f"{to_pvgis_aspect(azimuth)}")
    return f"{PVCALC_URL}?{urllib.parse.urlencode(params)}"


Opener = Callable[[str], dict[str, Any]]


def http_json(url: str) -> dict[str, Any]:
    # Fixed https:// PVGIS URL built by pvcalc_url().
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        return json.load(resp)


def fetch_with_retry(
    url: str,
    opener: Opener = http_json,
    retries: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """GET with exponential backoff on HTTP 429/5xx and network errors."""
    delay = 2.0
    for attempt in range(retries + 1):
        try:
            return opener(url)
        except urllib.error.HTTPError as e:
            retryable = e.code == 429 or e.code >= 500
            if not retryable or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        sleep(delay)
        delay *= 2
    raise AssertionError("unreachable")


def build_grid(
    opener: Opener = http_json,
    pause_s: float = 0.2,
    sleep: Callable[[float], None] = time.sleep,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Query PVGIS for every grid point, azimuth and tilt.

    ``pause_s`` keeps us at ~5 requests/s, far below the 30/s limit: this is
    a free public service.
    """
    total = len(LATS) * len(LONS) * len(AZIMUTHS) * len(TILTS)
    annual: list = []
    monthly: list = []
    done = 0
    for lat in LATS:
        row_a, row_m = [], []
        for lon in LONS:
            cell_a, cell_m = [], []
            for az in AZIMUTHS:
                tilt_a, tilt_m = [], []
                for tilt in TILTS:
                    result = parse_pvcalc(
                        fetch_with_retry(pvcalc_url(lat, lon, az, tilt), opener, sleep=sleep)
                    )
                    tilt_a.append(round(result.annual_kwh_per_kwp, 1))
                    tilt_m.append([round(v, 1) for v in result.monthly_kwh_per_kwp])
                    done += 1
                    if progress:
                        progress(done, total)
                    sleep(pause_s)
                cell_a.append(tilt_a)
                cell_m.append(tilt_m)
            row_a.append(cell_a)
            row_m.append(cell_m)
        annual.append(row_a)
        monthly.append(row_m)
    return {
        "format": "balkon-pvgis-grid",
        "version": 1,
        "attribution": ATTRIBUTION,
        "source": f"{PVCALC_URL} (PVGIS 5.3, PVGIS-SARAH3 2005-2023)",
        "params": {k: v for k, v in BASE_PARAMS.items() if k != "outputformat"},
        "unit": "kWh per kWp",
        "azimuthConvention": "degrees clockwise from north (app convention)",
        "lats": LATS,
        "lons": LONS,
        "azimuths": AZIMUTHS,
        "tilts": TILTS,
        # [lat][lon][azimuth][tilt]
        "annual": annual,
        # [lat][lon][azimuth][tilt][month 0..11]
        "monthly": monthly,
    }
