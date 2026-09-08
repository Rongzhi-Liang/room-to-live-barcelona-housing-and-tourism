# Room to Live

**Tourist homes and the geography of renting in Barcelona**

Rongzhi Liang · National University of Singapore · September 2026  
[Live story](https://rongzhi-liang.github.io/room-to-live-barcelona-housing-and-tourism/) · [中文](README_ZH.md)

A bilingual, fourteen-chapter map story exploring where tourist homes concentrate, how those places overlap with rental pressures, and what it takes to turn tourist accommodation into lasting homes. It combines official housing and rental statistics, Airbnb observations and documented neighbourhood experiences across Barcelona's 73 neighbourhoods.

Among 66 comparable neighbourhoods, tourist-home registration intensity is more closely associated with 2025 rent levels than with 2022–2025 rent growth (Spearman ρ = 0.74 and 0.10, respectively). These spatial associations do not establish a causal effect.

## Reproduce

Reference environment: macOS, R 4.6.1, Python 3.13.1, Node.js 24.19.0, pnpm 11.19.0 and QGIS 3.44.12. R spatial libraries: GEOS 3.13.0, GDAL 3.8.5 and PROJ 9.5.1. Package versions are fixed in `renv.lock` and `site/pnpm-lock.yaml`; Python uses its standard library.

Run from the repository root. Make `Rscript`, `node` and `pnpm` available on `PATH`; QGIS is detected at `/Applications/QGIS.app`. Other executable locations can be set through `RSCRIPT`, `NODE_BINARY`, `PNPM` and `QGIS_PYTHON`.

1. Restore R packages with an existing `renv` installation if their versions differ:

   ```sh
   Rscript -e 'dir.create(".r-library", showWarnings=FALSE); renv::restore(lockfile="renv.lock", library=".r-library", prompt=FALSE)'
   ```

2. Copy `site/.env.example` to `site/.env.local`. Enter a public Mapbox token in `VITE_MAPBOX_TOKEN`, with access to the preview origin. Keep `VITE_MAPBOX_SOURCE_MODE=local` to display the rebuilt GeoJSON.
3. Build and preview:

   ```sh
   python3 reproduce.py
   cd site
   pnpm exec vite preview --host 127.0.0.1 --port 4173 --strictPort
   ```

Open [127.0.0.1:4173](http://127.0.0.1:4173/). Frozen inputs are included in `data/inputs.zip`; installing dependencies and loading the basemap require internet access. The build checks the data and results, then produces research outputs in `build/research/`, a QGIS project in `build/qgis/`, Mapbox upload files in `build/mapbox/`, and the complete website in `site/dist/`.

## Publish

To build this GitHub Pages site, run from the repository root:

```sh
python3 reproduce.py --base /room-to-live-barcelona-housing-and-tourism/
```

Keep source files on `main`. Put the contents of `site/dist/` and an empty `.nojekyll` file at the root of `gh-pages`, then select that branch in GitHub Pages settings. Use your repository name in the base path and allow the published origin in the Mapbox token settings.

To use your own Mapbox Studio tilesets, upload the four GeoJSON files from `build/mapbox/` and update `tilesetId` and `sourceLayer` in `site/public/mapbox/registry.json`. Reassemble the style:

```sh
python3 analysis/assemble_style.py --base site/public/mapbox/base.style.json --registry site/public/mapbox/registry.json --data-dir site/public/data --out build/mapbox/room-to-live.style.json
```

Import `build/mapbox/room-to-live.style.json` into Studio and publish it. Update `site/public/mapbox/production.json` with the Style URL, set `VITE_MAPBOX_SOURCE_MODE=published`, and rebuild.

## Sources and licences

The [input manifest](data/inputs.json) records source dates, checksums and retained columns. Airbnb and register files retain all records and selected values; original rental workbooks and administrative polygons are preserved. The [source catalogue](config/sources.json) contains the story's references, and the [study definition](config/study.json) records its analytical settings.

| Material | Attribution and terms |
| --- | --- |
| Airbnb observations | [Inside Airbnb](https://insideairbnb.com/get-the-data/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| Tourist-home register and housing counts | Ajuntament de Barcelona · Open Data BCN, CC BY 4.0 |
| Administrative boundaries | Ajuntament de Barcelona · [CartoBCN](https://w20.bcn.cat/CartoBCN/), [reuse terms](https://w133.bcn.cat/geoportal/descargas/en_gb_cond_us_carto.pdf) |
| Rental statistics | Generalitat de Catalunya / INCASÒL, [public-information reuse terms](https://web.gencat.cat/ca/avis-legal) |
| DM Sans and Instrument Serif | Original authors; SIL Open Font License 1.1, with full notices in [fonts](site/public/fonts/) |
| Mapbox GL JS and basemap | [Mapbox terms](https://www.mapbox.com/legal/tos/) and package licence; Mapbox and OpenStreetMap contributor attribution retained |

Third-party material retains its own terms. Credit the data providers and identify changes when reusing their data. Reporting and public documents are cited through links and paraphrases; full articles and publisher PDFs are not included.
