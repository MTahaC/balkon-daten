# Attribution & licences

The pipeline downloads and processes the following data. The app shows the
same credits in its map attribution and its "Quellen & Lizenzen" page.

## Data

| Data                                                                          | Provider                                                                                                               | License                                                                                                    | Used for                                                                                               |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 3D-Gebäudemodell LoD2 NRW (CityGML, 1×1 km tiles)                             | Land NRW / Geobasis NRW, [opengeodata.nrw.de](https://www.opengeodata.nrw.de/produkte/geobasis/3dg/lod2_gml/lod2_gml/) | [Datenlizenz Deutschland – Zero – Version 2.0](https://www.govdata.de/dl-de/zero-2-0)                      | Building footprints and heights (map, shading)                                                         |
| Basemap (streets, water, land use, labels), Protomaps build 20261025          | © OpenStreetMap contributors, packaged by [Protomaps](https://protomaps.com) (`build.protomaps.com`)                   | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/)                                                     | Map background for orientation (`basemap.pmtiles`, extract around the data tiles, built at build time) |
| Gebäudereferenzen NRW (addresses with coordinates)                            | Land NRW / Geobasis NRW, [opengeodata.nrw.de](https://www.opengeodata.nrw.de/produkte/geobasis/lk/akt/gebref_txt/)     | [Datenlizenz Deutschland – Zero – Version 2.0](https://www.govdata.de/dl-de/zero-2-0)                      | Address search (`addresses.json`, only addresses inside the data tiles)                                |
| PVGIS 5.3 PV yield estimates (SARAH3, 2005–2023)                              | European Commission, Joint Research Centre                                                                             | Reuse authorised with acknowledgement ([EC reuse notice](https://data.jrc.ec.europa.eu/licence/com_reuse)) | Sanity check of annual estimates (static grid, built at build time)                                    |

dl-de/zero-2-0 permits any use without conditions and does not require
attribution; the sources are credited anyway.

## Build-time tools (not shipped)

| Tool                                                                                     | Version                | License                                                             |
| ---------------------------------------------------------------------------------------- | ---------------------- | ------------------------------------------------------------------- |
| tippecanoe (felt)                                                                        | 2.79.0                 | BSD-2-Clause                                                        |
| go-pmtiles (pmtiles CLI)                                                                 | 1.31.2                 | BSD-3-Clause                                                        |
| lxml                                                                                     | 6.1.3                  | BSD-3-Clause                                                        |
| numpy                                                                                    | 2.5.3                  | BSD-3-Clause (and bundled permissive licenses)                      |
| pyproj (incl. PROJ)                                                                      | 3.8.0                  | MIT                                                                 |
| shapely (incl. GEOS)                                                                     | 2.1.2                  | BSD-3-Clause (GEOS: LGPL-2.1, used as a library at build time only) |
