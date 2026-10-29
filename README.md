# balkon-daten

Data pipeline for **Balkon-Ertrag-Check**, an app that estimates what a
balcony solar system yields on a specific balcony. This repository turns the
open LoD2 3D building models of the German federal states into the compact
data releases the app loads: building prisms with roof faces for the shading
analysis, display tiles, the address index and the manifest.

The pipeline is public because its input is open data; the app itself lives
in a private repository. See [LICENSE](LICENSE) (code: all rights reserved)
and [ATTRIBUTION.md](ATTRIBUTION.md) (data sources and their licences).

## Layout

| Path | What |
| --- | --- |
| `pipeline/lod2pipe/` | LoD2 CityGML → data release (`python -m lod2pipe`) |
| `pipeline/pvgisgrid/` | PVGIS yield grid used as a sanity check by the app |
| `contract/` | Constants and a golden data release shared with the app's tests |
| `docs/data-contract.md` | The release format |
| `.github/workflows/data.yml` | Builds a release and publishes it as a GitHub release `data-<id>` |
| `.github/workflows/data-deploy.yml`, `site/` | Serves the newest releases from Cloudflare Pages |

## Running locally

tippecanoe doesn't run on Windows, so the full pipeline needs Linux or WSL2
(Ubuntu 24.04 or newer):

```bash
pipeline/setup.sh                 # apt packages, tippecanoe, pmtiles, Python venv
export PATH="$HOME/.local/bin:$PATH"
cd pipeline
.venv/bin/pytest -q               # tests
.venv/bin/python -m lod2pipe      # tiles from tiles.txt → out/release/
.venv/bin/python -m lod2pipe --municipality Köln --jobs 4 --delete-downloads
.venv/bin/python -m lod2pipe.chunks ../out/release --keep   # archives in pieces, as deployed
```

For the app's local development, pass the app's data folder as `--out`
(e.g. `--out ../../balkon-ertrag-check/app/public/data`).

Python dependencies: direct ones in `pipeline/requirements.in`;
`requirements.txt` pins all of them with hashes and is generated with the
`uv pip compile` command given at the top of `requirements.in`. The Python
parts (tests, ruff, basemap and address steps) also run on Windows in a plain
Python 3.12 venv; only tippecanoe needs Linux.

## Data site

`Data Deploy` (`.github/workflows/data-deploy.yml`) puts the newest two data
releases on the Cloudflare Pages project `balkon-daten`
(`https://balkon-daten.pages.dev/releases/<id>/…`, headers in
`site/_headers`: CORS for any origin, `immutable` caching, `noindex`). It
runs after every successful Data run on `main`, or by hand. One-time setup:
add `CLOUDFLARE_API_TOKEN` (Account → Cloudflare Pages → Edit) and
`CLOUDFLARE_ACCOUNT_ID` as secrets of the environment `data-pages` (Settings →
Environments), which only `main` can use. The app reads the data from there
once its repository variable `DATA_BASE_URL` points to the site.

## All of NRW

`Data NRW` (`.github/workflows/data-nrw.yml`, started by hand) builds the
analysis tiles of every NRW tile as a matrix: `lod2pipe --all --shard I/N`
splits the portal's tiles into N runs of about equal CityGML size in
Hilbert order (24 shards ≈ 9 GB each), and each shard packs its own v3
pieces (`lod2pipe.pack`). At most `parallel` shards (default 8) download
from the portal at once; downloads are retried 8 times with backoff. Each
shard uploads `analysis-shard-<i>` (pieces, index, manifest; 14 days), and
the summary job adds up tiles, pieces, size and the slowest shard. A failed
shard can be re-run on its own ("Re-run failed jobs"). Merging the shards
into a data release, with the address index per municipality, is a
separate step.
