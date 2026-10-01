# VienneseDataCrunch

Interactive map of Vienna addresses extracted from *Lehmann's Wohnungsanzeiger*
(Vienna's address books), 1938–1942.

**Live site:** https://mosheberman.github.io/VienneseDataCrunch/

## What it is

Every pin is a Vienna address with one or more people or businesses listed in the
Lehmann directories. The year picker switches between full layers for 1938–1942,
and each record popup shows the scanned row it came from.

- **Search** by surname, street, and occupation, with unit numbers (Stg./Tür/Top)
  where the book lists them
- **Follow this person** — an animated 1938→1942 timeline; the travelling dot
  follows streets (A\* routing over Vienna's street graph), with arrival popups
  per year
- **Scan excerpts** — cropped row images from the original scans, plus a link to
  the full scan page
- **Corrections** — suggest a correction inline on any record; submissions are
  reviewed before they appear on the map
- **Overlays** — Nazi-era street renames traced as lines, and historical sites
  (Sammellager, Aspangbahnhof, Gestapo HQ)
- **Bilingual UI** — English / Deutsch

## Screenshots

Desktop:

| Map | Search |
| --- | ------ |
| ![Map of central Vienna with address pins](screenshots/map.png) | ![Search results for "Bermann"](screenshots/search.png) |

| Record | Follow this person |
| ------ | ------------------ |
| ![Record popup with scan excerpt](screenshots/record.png) | ![Follow panel with year timeline](screenshots/follow.png) |

| Street renames | German UI |
| -------------- | --------- |
| ![Nazi-era street rename overlays near Rathausplatz](screenshots/renames.png) | ![German-language interface](screenshots/german.png) |

Mobile:

| Point sheet | Follow journey |
| ----------- | -------------- |
| ![Bottom sheet with records for an address](screenshots/mobile-sheet.jpg) | ![Follow panel mid-animation with routed path](screenshots/mobile-follow.jpg) |

| Correction | Historical sites |
| ---------- | ---------------- |
| ![Suggest-a-correction modal](screenshots/mobile-correction.jpg) | ![Gestapo HQ historical site](screenshots/mobile-gestapo.jpg) |

| German UI | Street renames |
| --------- | -------------- |
| ![Gestapo HQ in the German interface](screenshots/mobile-german.jpg) | ![Rathausplatz → Adolf Hitler-Platz rename overlay](screenshots/mobile-renames.jpg) |

From the book itself — a 1939 directory page showing the renamed street in print:

![1939 Lehmann page: "Böhmer Julius, Portier, I. Adolf Hitler-Platz 2"](screenshots/rename-book-page.png)

## How it's built

1. Scans of the Lehmann volumes from the Wienbibliothek's Retrodigitalisierung
   copies (public domain)
2. The library's per-page Transkribus ALTO OCR, with bounding boxes for every
   text line
3. Parsing of names, occupations, addresses and unit numbers; headers, footers
   and ads stripped
4. Street-name normalization — ambiguous forms held for review, not silently fixed
5. Geocoding against the City of Vienna address registry
6. Tiered pins: blue exact match, purple registry match, amber fuzzy-approximate

Caveats: OCR misreads names; some streets were renamed or no longer exist; amber
pins are approximate. A missing pin doesn't mean the entry is missing from the
book — not every address matched the modern registry.

## Data sources & attribution

Beyond the scans, the site is built on these public sources:

- **Street coordinates** — Stadt Wien, Open Government Data
  ([data.wien.gv.at](https://data.wien.gv.at)): the `STRASSENGRAPHOGD` street
  centerlines (rename-overlay geometries follow the real centerlines) and the
  City of Vienna address registry (geocoding). Geodata: © Stadt Wien,
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) —
  *Datenquelle: Stadt Wien – data.wien.gv.at*.
- **Basemap** — © [Mapbox](https://www.mapbox.com/), ©
  [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors
  ([ODbL](https://opendatacommons.org/licenses/odbl/)).
- **Historical street renames** — research draws on the 10 December 1938
  street-renaming decree and the
  [Wien Geschichte Wiki](https://www.geschichtewiki.wien.gv.at/) (Stadt Wien).
  Wiki article texts are
  [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/); only
  factual old→new name pairs are used, and the wiki's structured entry data is
  published as Open Government Data. Cross-checked against the German
  Wikipedia's Vienna street-name lists
  ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)).
- **Landmark images** — via [Wikimedia Commons](https://commons.wikimedia.org):
  Aspangbahnhof c. 1905 (public domain); Hotel Métropole c. 1873, via the
  Rijksmuseum ([CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)).

## Repository layout

- `index.html` — the site (single-file app)
- `data/`, `data39/`, `data40/`, `data41/`, `data42/`, … — per-year record shards
- `layers/` — GeoJSON overlays (street renames, historical sites, street graph)
- `research/` — draft explorers and experiments (unreviewed work in progress)
- `pipeline/` — build scripts

## Licensing

- **Scans:** Wienbibliothek im Rathaus —
  [Public Domain Mark 1.0](https://creativecommons.org/publicdomain/mark/1.0/).
  When reusing the scans, please credit the Wienbibliothek im Rathaus as the
  holding institution.
- **Extracted map data:** [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).

## Releases

Changes ship as tagged [semantic-versioned releases](../../releases)
(`vMAJOR.MINOR.PATCH`):

- **PATCH** — bug fixes, small corrections
- **MINOR** — new features, new overlays, new data layers
- **MAJOR** — breaking changes to data formats or URLs

The running site's version is shown in Settings → About → Licensing.
