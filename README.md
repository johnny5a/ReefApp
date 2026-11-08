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
`.github/workflows/update-reef-data.yml` runs `scripts/update_reef_data.py` on the 1st of every month (and on demand from the Actions tab). It downloads from reef.org:
- California dive sites and zone codes (`src/sites_ca.txt`)
- the Pacific Coast species list with REEF codes (`src/species_pac.txt`)
- species from REEF's other regions, offered as Unlisted species (`src/species_unlisted.txt`)
- how often each species is seen at each California site and area (`src/site_freq_ca.txt`), from REEF's Geographic Zone Reports

It then rebuilds `index.html` and commits only if something changed.

## Updating
- App code: `src/index.src.html`. Species list: `src/species_pac.txt`. California dive sites and zone codes: `src/sites_ca.txt` (from [REEF's zone code list](https://www.reef.org/db/zonecodes/list/?region_code=PAC)).
- Run `python3 build.py` to rebuild `index.html`, bump `VERSION` in `sw.js`, then commit and push. Phones pick up the new version the next time the app opens with signal.
