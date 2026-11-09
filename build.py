"""Build the app: python3 build.py

- index.html  ← src/index.src.html
- data/<REGION>.json  ← src/<REGION>/{sites,species,unlisted,freq}.txt (+ quick.txt, family_order.txt)
  The app loads one region's file at a time; the service worker keeps them all offline.
After building, bump VERSION in sw.js so phones pick up the change."""
import json
import re
from pathlib import Path

root = Path(__file__).parent
src = root / "src"
REGION_INFO = {
    # root: zone code the site browser starts from; near: regions whose species are likeliest strays
    "PAC": {"name": "California", "long": "California (Pacific Coast)", "root": "4", "near": ["TEP"],
            "habitats": ["Kelp Forest", "Rock Boulder/Shale Reef", "Artificial", "Open Ocean", "Eel Grass Bed", "Surf Grass Bed",
                         "Pinnacle", "Bull Kelp", "Sandy Bottom/Mud/Silt", "Cobblestone/Boulder Field", "Wall"]},
    "TWA": {"name": "Caribbean", "long": "Caribbean, Florida & Bahamas (TWA)", "root": "", "near": ["SAS", "NE"],
            "habitats": ["High Profile Reef", "Low Profile Reef", "Sloping Dropoff", "Wall", "Ledge", "Grass",
                         "Sandy Bottom/Mud/Silt/Mangrove", "Rubble", "Artificial", "Open Ocean", "Cobblestone/Boulder Fields/Escarpment"]},
}
QUICK_SIZE = 70
# "At this site" lists: species seen on at least FREQ_MIN_PCT% of a site's surveys, up to FREQ_TOP per site.
# Rarer species are still in search and "All". Keeps the Caribbean file small enough for phones.
FREQ_MIN_PCT, FREQ_TOP = 3, 80


def trim_freq(freq):
    out = []
    for line in freq.splitlines():
        zone, n, lst = line.split("|")
        items = [x for x in lst.split(",") if x and int(x.split(":")[1]) >= FREQ_MIN_PCT][:FREQ_TOP]
        if items:
            out.append(f"{zone}|{n}|{','.join(items)}")
    return "\n".join(out)


def read(p):
    return p.read_text().strip() if p.exists() else ""


def quick_codes(region, species, freq):
    """Common-species list: hand-picked names if given, else the most-seen species across the region's top areas."""
    by_name = {l.split("|")[1]: l.split("|")[0] for l in species.splitlines()}
    names = read(src / region / "quick.txt")
    if names:
        return [by_name[n] for n in names.splitlines() if n in by_name]
    total, score = 0, {}
    for line in freq.splitlines():
        zone, n, lst = line.split("|")
        if len(zone) != (len(REGION_INFO[region]["root"]) + 1):
            continue  # only the region's top-level areas
        n = int(n); total += n
        for item in lst.split(","):
            c, p = item.split(":")
            score[c] = score.get(c, 0) + int(p) * n
    return [c for c, _ in sorted(score.items(), key=lambda x: -x[1])[:QUICK_SIZE]] if total else []


def norm(name):
    return re.sub(r"[^a-z]", "", name.lower())


def form_order(region, species):
    """Map species codes to REEF survey-form groups: {"names": [...], "codes": {code: [group index, position]}}.
    Matched on scientific name, then on common name (REEF's form page uses some older names)."""
    rows = [l.split("|") for l in read(src / region / "form_groups.txt").splitlines() if l.count("|") == 2]
    if not rows:
        return None
    by_sci, by_name = {}, {}
    for l in species.splitlines():
        f = l.split("|")
        by_sci.setdefault(re.sub(r"\s*\(.*?\)", "", f[2]).strip().lower(), f[0])
        by_name.setdefault(norm(f[1]), f[0])
    names, codes = [], {}
    for group, common, sci in rows:
        sci = sci.strip(" -")
        if not (common or sci):
            continue
        if group not in names:
            names.append(group)
        code = by_sci.get(sci.strip().lower()) or by_name.get(norm(common))
        if code and code not in codes:
            codes[code] = [names.index(group), len(codes)]
    return {"names": names, "codes": codes}


(root / "data").mkdir(exist_ok=True)
date = read(src / "data_date.txt")
built = []
for region, info in REGION_INFO.items():
    d = src / region
    sites, species = read(d / "sites.txt"), read(d / "species.txt")
    if not (sites and species):
        continue
    freq, unlisted = read(d / "freq.txt"), read(d / "unlisted.txt")
    # REEF's data-entry family order, one family (scientific or common name) per line, if known
    fam_order = [l.strip() for l in read(d / "family_order.txt").splitlines() if l.strip()]
    coords = read(d / "coords.txt")
    freq = trim_freq(freq)
    data = {"region": region, **info, "date": date, "sites": sites, "species": species,
            "unlisted": unlisted, "freq": freq, "quick": quick_codes(region, species, freq), "famOrder": fam_order,
            "coords": coords, "formGroups": form_order(region, species)}
    (root / "data" / f"{region}.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    built.append(region)

regions = [{"code": r, "name": REGION_INFO[r]["name"], "long": REGION_INFO[r]["long"]} for r in built]
page = (src / "index.src.html").read_text().replace("/*REGIONS*/", json.dumps(regions))
(root / "index.html").write_text(page)
print("index.html built; data for", ", ".join(built) or "no regions")
