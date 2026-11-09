# REEF Dive Survey

A phone app for logging [REEF](https://www.reef.org) Volunteer Fish Survey dives (Pacific Coast / California) that works with no signal on the boat. Tap species with S / F / M / A, fill in site and conditions in the same order as REEF's data entry form, then enter the survey on REEF.org.

**Open it:** https://johnny5a.github.io/ReefApp/

## Install on iPhone
1. Open the link above in **Safari** while you have signal.
2. Tap **Share** → **Add to Home Screen** → **Add**.
3. Open it once from the Home Screen icon. After that it works offline.

## Data
- Surveys are stored only on the phone (in the app's own storage). Use **Back up** on the Log tab now and then and save the file to iCloud Drive; **Restore** reads it back on any device.
- **Copy data (JSON)** or **Copy all ready surveys for Claude** puts survey data on the clipboard to paste into Claude, which can fill in REEF's web form for you.

## Sources
- Survey fields: [REEF VFSP metadata descriptions](https://www.reef.org/vfsp-metadata-descriptions)
- Species: [REEF PAC names report](https://www.reef.org/db/reports/species?region_code=PAC) and [California invertebrate and algae list](https://www.reef.org/california-invertebrate-and-algae-monitoring-program)

## REEF data (updated automatically)
`.github/workflows/update-reef-data.yml` runs `scripts/update_reef_data.py` on the 1st of every month (and on demand from the Actions tab). For each region (California/PAC and Caribbean/TWA) it downloads from reef.org into `src/<REGION>/`:
- dive sites and zone codes (`sites.txt`)
- the region's species list with REEF codes (`species.txt`)
- species from REEF's other regions, offered as Unlisted species (`unlisted.txt`)
- how often each species is seen at each site and area with 5+ surveys (`freq.txt`), from REEF's Geographic Zone Reports
- site locations (`coords.txt`) from REEF's public data-entry site search, for the site map
- REEF's survey-form groups (`form_groups.txt`, e.g. Bass, Rockfish, Surf Perch) from REEF's species reference pages, for the Family sort

Monthly runs only re-download sites whose REEF survey count changed (typically 10–20 minutes); every January, or when you tick "full" under Actions → Update REEF data → Run workflow, it re-downloads everything (1–2 hours).

`build.py` turns these into `data/<REGION>.json`, which the app loads for the region you pick; the service worker keeps every region offline. The job commits only if something changed.

## Updating
- App code: `src/index.src.html`. Region data: `src/<REGION>/` (written by the updater; `src/PAC/quick.txt` is the hand-picked "Common in California" list).
- Run `python3 build.py` to rebuild `index.html` and `data/`, bump `VERSION` in `sw.js`, then commit and push. Phones pick up the new version the next time the app opens with signal.

## Third-party code
- `vendor/leaflet/`: [Leaflet](https://leafletjs.com) 1.9.4 (BSD-2-Clause, see its LICENSE), bundled so the map works offline. Map tiles © OpenStreetMap contributors.
