"""Build the app: python3 build.py

- index.html  ← src/index.src.html
- data/<REGION>.json  ← src/<REGION>/*.txt for every enabled region in regions.json
- data/regions.json   ← which region files the service worker keeps offline from the start
  The app loads one region's file at a time; the service worker keeps them all offline.
After building, bump VERSION in sw.js so phones pick up the change."""
import json
import re
from pathlib import Path

root = Path(__file__).parent
src = root / "src"
CONFIG = json.loads((root / "regions.json").read_text())["regions"]


def region_info(r):
    """App-facing settings for one regions.json entry. `root` is where the site browser starts
    (California starts inside zone 4; whole REEF regions start at their top-level areas)."""
    prefixes = r.get("prefixes", [])
    habitats = [l.strip() for l in read(src / r["id"] / "habitats.txt").splitlines() if l.strip()] or r.get("habitats", [])
    return {"name": r["name"], "long": r.get("long", r["name"]), "root": prefixes[0] if len(prefixes) == 1 else "",
            "near": r.get("near", []), "habitats": habitats, "surveyTypes": r.get("survey_types", []),
            "example": r.get("example", "Site name, area, or zone code")}


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
        if len(zone) != (len(root_of[region]) + 1):
            continue  # only the region's top-level areas
        n = int(n); total += n
        for item in lst.split(","):
            c, p = item.split(":")
            score[c] = score.get(c, 0) + int(p) * n
    return [c for c, _ in sorted(score.items(), key=lambda x: -x[1])[:QUICK_SIZE]] if total else []


# ---------- Site locations: REEF's records contain some typing mistakes; fix the obvious ones ----------
import math, statistics


def dist_km(a, b):
    r = math.pi / 180
    x = (b[1] - a[1]) * r * math.cos((a[0] + b[0]) / 2 * r); y = (b[0] - a[0]) * r
    return math.hypot(x, y) * 6371


def in_bounds(p, b):
    (la0, lo0), (la1, lo1) = b
    lon_ok = lo0 <= p[1] <= lo1 if lo0 <= lo1 else (p[1] >= lo0 or p[1] <= lo1)   # lo1 < lo0: crosses the date line
    return la0 <= p[0] <= la1 and lon_ok


COORD_FIXES = [
    ("degrees typed as minutes", lambda a, o: (a * 60, o * 60)),
    ("latitude degrees typed as minutes", lambda a, o: (a * 60, o)),
    ("longitude degrees typed as minutes", lambda a, o: (a, o * 60)),
    ("longitude sign missing", lambda a, o: (a, -o)),
    ("latitude sign wrong", lambda a, o: (-a, o)),
    ("latitude and longitude swapped", lambda a, o: (o, a)),
    ("swapped, signs flipped", lambda a, o: (-o, -a)),
]


def clean_coords(region, raw, bounds, names):
    """Returns (lines for the app, issues for REEF). A location is suspect if it lies outside the region, or far
    from the other sites in its REEF area. Suspects are fixed if one of the usual typing mistakes explains them;
    fixes that only keep whole degrees (degrees typed as minutes) use the middle of the site's area instead and
    are marked approximate. Unfixable impossible locations are dropped (the site stays in the list, no dot)."""
    co = {}
    for l in raw.splitlines():
        c, la, lo = l.split("|"); co[c] = (float(la), float(lo))
    good = {c: p for c, p in co.items() if not bounds or in_bounds(p, bounds)}

    def area(c):
        for k in range(len(c) - 1, 0, -1):
            pts = [p for x, p in good.items() if x.startswith(c[:k]) and x != c]
            if len(pts) >= 3:
                cen = (statistics.median(p[0] for p in pts), statistics.median(p[1] for p in pts))
                return c[:k], cen, statistics.median(dist_km(cen, p) for p in pts)
        return None, None, None

    lines, issues = [], []
    for c, p in co.items():
        acode, cen, spread = area(c)
        outside = bool(bounds) and not in_bounds(p, bounds)
        far = cen is not None and dist_km(p, cen) > max(400, 8 * spread)
        if not (outside or far):
            lines.append(f"{c}|{p[0]}|{p[1]}"); continue
        cands = [(n, f(*p)) for n, f in COORD_FIXES]
        cands = [(n, q) for n, q in cands if not bounds or in_bounds(q, bounds)]
        if cen is not None:
            cands = sorted(((n, q) for n, q in cands if dist_km(q, cen) <= max(150, 4 * spread)), key=lambda t: dist_km(t[1], cen))
        if cands:
            why, q = cands[0]
            whole = abs(q[0] - round(q[0])) < 0.01 and abs(q[1] - round(q[1])) < 0.01
            if whole and cen is not None:
                q = cen; note = "approximate: placed at the middle of its REEF area"
            else:
                note = "corrected"
            lines.append(f"{c}|{round(q[0], 4)}|{round(q[1], 4)}|a" if whole else f"{c}|{round(q[0], 4)}|{round(q[1], 4)}")
            issues.append((c, names.get(c, ""), p, why, note, q))
        elif not outside:
            lines.append(f"{c}|{p[0]}|{p[1]}")               # far from its neighbours but possible: keep REEF's location
        else:
            issues.append((c, names.get(c, ""), p, "outside the region; no likely fix", "left off the map", None))
    return "\n".join(lines), issues


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
built, manifest, root_of, all_issues = [], [], {}, {}
for r in CONFIG:
    region = r["id"]
    if not r.get("enabled"):
        continue
    info = region_info(r)
    root_of[region] = info["root"]
    d = src / region
    sites, species = read(d / "sites.txt"), read(d / "species.txt")
    if not (sites and species):
        continue
    freq, unlisted = read(d / "freq.txt"), read(d / "unlisted.txt")
    # REEF's data-entry family order, one family (scientific or common name) per line, if known
    fam_order = [l.strip() for l in read(d / "family_order.txt").splitlines() if l.strip()]
    names = dict(l.split("|", 1) for l in sites.splitlines())
    coords, issues = clean_coords(region, read(d / "coords.txt"), r.get("bounds"), names)
    all_issues[region] = (info, issues)
    freq = trim_freq(freq)
    data = {"region": region, **info, "date": date, "sites": sites, "species": species,
            "unlisted": unlisted, "freq": freq, "quick": quick_codes(region, species, freq), "famOrder": fam_order,
            "coords": coords, "formGroups": form_order(region, species)}
    (root / "data" / f"{region}.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    built.append({"code": region, "name": info["name"], "long": info["long"], "surveyTypes": info["surveyTypes"]})
    manifest.append({"file": f"data/{region}.json", "precache": bool(r.get("precache"))})

# A list of REEF location records that look wrong, to send to REEF (zonecode@REEF.org).
rep = ["# REEF site locations that look wrong", "",
       "Found automatically by `build.py` when the app's data is built: each site's latitude/longitude from REEF's",
       "data-entry site search is checked against its region and the other sites in its REEF area.",
       "The app uses the corrected location shown here; REEF's record itself still needs fixing.", "",
       "To report them, send this list to zonecode@REEF.org.", ""]
for region, (info, issues) in all_issues.items():
    rep += [f"## {info['long']}", ""]
    if not issues:
        rep += ["No problems found.", ""]; continue
    rep += ["| Zone code | Site | REEF has (lat, lon) | Likely mistake | App uses |", "|---|---|---|---|---|"]
    for c, n, p, why, note, q in sorted(issues):
        used = f"{q[0]:.4f}, {q[1]:.4f} ({note})" if q else note
        rep.append(f"| {c} | {n} | {p[0]}, {p[1]} | {why} | {used} |")
    rep.append("")
(root / "docs").mkdir(exist_ok=True)
(root / "docs" / "reef-location-issues.md").write_text("\n".join(rep))

# The service worker reads this to know which region files to keep offline from the start;
# other regions are kept once you open them.
(root / "data" / "regions.json").write_text(json.dumps(manifest))
regions = built
page = (src / "index.src.html").read_text().replace("/*REGIONS*/", json.dumps(regions))
(root / "index.html").write_text(page)
print("index.html built; data for", ", ".join(r["code"] for r in built) or "no regions")
