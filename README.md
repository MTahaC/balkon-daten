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
