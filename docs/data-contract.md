# Data contract: pipeline ↔ app

Everything the pipeline (Python, `pipeline/` in this repository) writes and
the app (TypeScript, `app/` in the private app repository, which pins this
repository as a git submodule) reads. Both sides are checked against the same
files:

- **`contract/constants.json`** – values both must agree on; tested by
  `pipeline/tests/test_contract.py` and `app/src/data/contract.test.ts`.
- **`contract/fixtures/`** – a tiny golden data release built from
  `pipeline/tests/fixtures/mini_tile.gml`. The pipeline test rebuilds it and
  compares byte for byte (except `generatedAt`); the app test parses it,
  searches its addresses and reassembles its archive from the pieces.

A format change on one side breaks a test. After a deliberate change:
update both sides, bump the format version, regenerate the fixtures with
`UPDATE_CONTRACT=1 pytest tests/test_contract.py`, and run Data for a new
release.

## Shared values

| Value                    | Contract                             | Pipeline                              | App                                   |
| ------------------------ | ------------------------------------ | ------------------------------------- | ------------------------------------- |
| LoD2 tile size, key      | 1000 m, `EEE_NNNN`                   | `tiles.TILE_SIZE_M`, `TileId.key`     | `geo/lod2Tiles.ts`                    |
| Shading radius + margin  | 300 m + 100 m                        | covered by `with_neighbours(rings=1)` | `geo/obstacleEdges.ts`                |
| Analysis format, version | `balkon-lod2-prisms`, 2              | `export.ANALYSIS_FORMAT/VERSION`      | `data/analysisTiles.ts`               |
| Address format, version  | `balkon-addresses`, 1                | `addresses.FORMAT/VERSION`            | `search/addressSearch.ts`             |
| Display layer            | `buildings`                          | `__main__.LAYER`                      | `data/displayTiles.ts`                |
| Piece size, naming       | 65536, `<archive>.chunks/000007.bin` | `chunks.py`                           | `data/sources/chunkedSource.ts`       |
| System loss              | 14 %                                 | `pvgisgrid` (`loss=14`)               | `solar/pvModel.ts` (`DEFAULT_SYSTEM`) |

One ring of neighbour tiles (1 km) must cover the shading radius plus
margin (400 m); both tests check it.

## Release layout

```
releases/<id>/                      id = yyyymmdd-hhmm-<commit>
  manifest.json
  buildings.pmtiles.chunks/000000.bin …   (or buildings.pmtiles, whole)
  basemap.pmtiles.chunks/000000.bin …
  analysis/<EEE>_<NNNN>.json           (format v2, one file per tile)
  analysis/index.json                 (format v3: tile → piece, offset, length)
  analysis/pieces/<sha256:16>.bin      (format v3: ~1 MiB of gzip members)
  addresses.json
```

The site serves it below `/data/releases/<id>/`; `/data/manifest.json` is a
copy of the release's manifest (decision 0009).

## manifest.json

| Field                           | Type           | Meaning                                                          |
| ------------------------------- | -------------- | ---------------------------------------------------------------- |
| `generatedAt`                   | ISO 8601       | build time; part of the horizon cache key                        |
| `release`                       | string \| null | release id (files under `releases/<id>/`); null for local builds |
| `coverage`                      | string \| null | covered area for texts ("Köln")                                  |
| `bounds`                        | [w, s, e, n]   | WGS84 box of all tiles                                           |
| `tiles`                         | string[]       | processed tile keys                                              |
| `pmtiles`                       | string \| null | building archive name                                            |
| `analysisPath`                  | string         | path template with `{tile}`                                      |
| `analysisIndex`                 | string | absent | v3 index (`analysis/index.json`); absent = v2 only            |
| `attribution`                   | HTML           | LoD2 credit with the data year                                   |
| `basemap`, `basemapAttribution` | string \| null | basemap archive and credit                                       |
| `addresses`                     | string \| null | address index file                                               |
| `chunks`                        | object \| null | `{size, archives: {name: bytes}}`; null = whole archives         |

## Analysis tile (`balkon-lod2-prisms`, version 2)

```jsonc
{
  "format": "balkon-lod2-prisms", "version": 2,
  "tile": "356_5644", "crs": "EPSG:25832", "heightReference": "DHHN2016 (NHN)",
  "origin": [356000, 5644000],            // add to x/y to get EPSG:25832
  "buildings": [{
    "id": "DENW37AL1000sKnL",              // BuildingPart or Building gml:id
    "groundZ": 53.5, "eaveZ": 69.59, "ridgeZ": 69.59,   // absolute, m NHN
    "function": "31001_2000",              // ALKIS/ATKIS function code or null
    "polygons": [[[[325.95, 810.61], ...]]], // MultiPolygon, closed rings, CCW exteriors, CW holes
    "roofs": [[[[325.95, 810.61, 69.59], ...]]] // roof faces > rings > [x, y, z absolute]
  }]
}
```

Coordinates in metres relative to `origin` (cm precision). A building
belongs to exactly one tile and is not clipped at its edge.

## Packed analysis tiles (format version 3)

The same content as v2, written by `lod2pipe.pack` from the v2 tiles; the
encoding is described at the top of `pipeline/lod2pipe/pack.py`. In short:
one gzip member per tile (LEB128 varints, zig-zag for signed values,
centimetres, ring points as deltas, roof z relative to `groundZ`, closed
rings without their repeated last point), members concatenated in Hilbert
order into pieces of at most 1 MiB (`analysisPieceSize`; a bigger tile gets
a piece of its own), pieces named by the first 16 hex digits of their
SHA-256.

```jsonc
// analysis/index.json
{
  "format": "balkon-lod2-prisms", "version": 3,
  "pieces": ["49fe4aaeaa0280e5.bin"],
  "tiles": { "356_5644": [0, 0, 327] }   // [piece, byte offset, byte length]
}
```

Decoding gives exactly the v2 values (cm integers divided by 100), so v2
and v3 give identical horizons. Releases carry both while app versions
without v3 are still in use.

## Display tiles (`buildings.pmtiles`)

Layer `buildings`, WGS84, zoom 13–16. Properties: `id`, `h` (ridge height
above ground, m), `h_eave`, `roof` (roof type code), `fn` (function code),
`area` (footprint, m²). Parts under 50 m² (z13) and 25 m² (z14) are left
out (decision 0011).

## Address index (`balkon-addresses`, version 1)

```jsonc
{
  "format": "balkon-addresses",
  "version": 1,
  "crs": "EPSG:25832",
  "origin": [356000, 5644000],
  // [street, municipality, [[number, suffix, x, y], …]], x/y in metres
  // (0.1 m precision) relative to origin, numbers sorted numerically
  "streets": [
    [
      "Heumarkt",
      "Köln",
      [
        ["1", "", 15.0, 15.0],
        ["1", "a", 30.0, 15.0],
      ],
    ],
  ],
}
```

## Naming

- **Building part / prism:** one LoD2 `bldg:BuildingPart` (or a building
  without parts). The pipeline calls it a prism; JSON and the app call the
  list `buildings`. Same thing.
- **Key style:** JSON files use camelCase (`groundZ`, `analysisPath`);
  vector-tile properties use short keys (`h`, `h_eave`, `fn`) because every
  byte is repeated per feature. Existing keys stay as they are (renaming is a
  format change); new fields follow this rule.
