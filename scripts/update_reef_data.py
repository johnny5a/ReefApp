"""Refresh the REEF data the app ships with, straight from reef.org.

For each region in REGIONS it writes src/<REGION>/:
  sites.txt      Geographic Zone Codes                    code|name
  species.txt    the region's species list (REEF codes)   code|common|scientific|family|family common name
  unlisted.txt   species from REEF's other regions        common|scientific|family|regions
  freq.txt       how often each species is seen per site  zone|surveys|code:pct,code:pct,...
                 or area (Geographic Zone Report, total SF%), for zones with enough surveys
  coords.txt     site locations from REEF's data-entry site search   code|lat|lon
  form_groups.txt  REEF's survey-form groups, in form order  group|common|scientific
and src/data_date.txt.

Regions come from regions.json (entries with "enabled": true). Area codes, habitats, form groups and
the common-species list are worked out from REEF's own pages, so a new region needs only its entry.

Run:  python3 scripts/update_reef_data.py [--full] [PAC TWA ...]   then  python3 build.py

Incremental by default: the big area reports give every zone's survey count, and only zones
whose count changed since the last run (or that are new) get their species report re-fetched.
--full re-fetches every zone (the workflow does this each January, or on request).
Standard library only. Requests are sequential with a pause, to be gentle on reef.org.
"""
import datetime, html.parser, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = "https://www.reef.org"
SRC = Path(__file__).resolve().parent.parent / "src"
UA = "ReefApp data updater (https://github.com/johnny5a/ReefApp)"
PAUSE = 0.4            # seconds between requests
MIN_SURVEYS = 5        # the app falls back to the parent area below this
MAX_SPECIES = 150      # per zone, most-seen first
ALL_REGIONS = ["TWA", "PAC", "HAW", "TEP", "SOP", "NE", "SAS", "CIP", "EAM", "IORS"]

DATA = "https://data.reef.org"
CONFIG = Path(__file__).resolve().parent.parent / "regions.json"


def load_regions():
    """Enabled regions from regions.json, keyed by app id. `reef` is REEF's region code; `prefixes` limits
    zones (e.g. California = zones starting with 4); no prefixes = the whole REEF region."""
    out = {}
    for r in json.loads(CONFIG.read_text())["regions"]:
        if r.get("enabled"):
            out[r["id"]] = {"reef": r.get("reef", r["id"]), "prefixes": r.get("prefixes", []),
                            "survey_id": str(r.get("survey_id", "1")),
                            "form_page": r.get("form_page") or f"{r.get('reef', r['id']).lower()}/fishsp.htm"}
    return out


def line_count(path):
    return len(path.read_text().splitlines()) if path.exists() else 0


class Tables(html.parser.HTMLParser):
    """Collects every <table> as a list of rows, each row a list of cell texts."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._stack, self._row, self._cell = [], [], None, None
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())
    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def get(path, tries=3, timeout=240):
    url = path if path.startswith("http") else BASE + path
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8", "replace")
            time.sleep(PAUSE)
            return text
        except Exception as e:
            if attempt == tries - 1:
                raise
            print(f"  retry {url}: {e}", file=sys.stderr, flush=True)
            time.sleep(10 * (attempt + 1))


def tables(path):
    p = Tables()
    p.feed(get(path))
    return p.tables


def clean(s):
    return " ".join(str(s).replace("|", "/").replace("`", "'").replace("${", "$ {").split())


def as_int(x):
    x = x.replace(",", "")
    return int(x) if x.isdigit() else None


_zone_cache = {}
def zone_list(reef, prefixes):
    if reef not in _zone_cache:
        rows = [r for t in tables(f"/db/zonecodes/list/?region_code={reef}") for r in t]
        # columns: Zone | Zone Code list | Geographic Report | Name | Have Coordinates?
        _zone_cache[reef] = [(r[0], clean(r[3])) for r in rows if len(r) >= 4 and r[0].isdigit() and r[0] != "0"]
    return [z for z in _zone_cache[reef] if not prefixes or any(z[0].startswith(p) for p in prefixes)]


def species(region):
    rows = [r for t in tables(f"/db/reports/species?region_code={region}") for r in t]
    # columns: Image | Species ID | Common | Scientific | Family common | Family scientific | ...
    return [(r[1], clean(r[2]), clean(r[3]), clean(r[5]), clean(r[4])) for r in rows
            if len(r) >= 6 and r[1].isdigit() and 3 <= len(r[1]) <= 5]


def geo_report(region, zone, today):
    """Returns ({zone: surveys} for every zone listed, [(species code, SF%)] for `zone`)."""
    q = urllib.parse.urlencode({"end_date": today, "format_type": "table", "group_type": "species",
                                "language": "common", "region_code": region, "start_date": "1993-01-01", "zones": zone})
    ts = tables("/db/reports/geo?" + q)
    if len(ts) < 2:
        return {}, []
    counts = {}
    # Table 0: Code | Name | survey counts ... | bottom time (H:M)
    for r in ts[0]:
        if len(r) >= 4 and r[0].isdigit():
            counts[r[0]] = sum(v for v in (as_int(x) for x in r[2:-1]) if v)
    sp = []
    # Table 1: Rank | Species ID | Species | Family | SF% | DEN | ...
    for r in ts[1]:
        if len(r) >= 5 and r[0].isdigit():
            try:
                sp.append((r[1], round(float(r[4]))))
            except ValueError:
                pass
    return counts, sp


def freq_line(zone, n, sp):
    sp = [x for x in sp if x[1] >= 1][:MAX_SPECIES]
    return f"{zone}|{n}|" + ",".join(f"{c}:{p}" for c, p in sp) if sp else None


def read_old_freq(path):
    """zone -> (surveys, line) from the previous run, if any."""
    old = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split("|")
            if len(parts) == 3 and parts[1].isdigit():
                old[parts[0]] = (int(parts[1]), line)
    return old


def site_coords(cfg, tops):
    """REEF's data-entry site search lists each site with a map link carrying lat/lon. Public, no login needed.
    Its region dropdown values are the region's top-level area codes."""
    out = {}
    for reg in tops:
        h = get(f"{DATA}/cgi-bin/autocomplete.pl?q=&region={reg}&surveyid={cfg['survey_id']}&t=1")
        for m in re.finditer(r"zonecode=(\d+)&(?:amp;)?name=[^&]*&(?:amp;)?lat=(-?[\d.]+)&(?:amp;)?lon=(-?[\d.]+)", h):
            lat, lon = float(m.group(2)), float(m.group(3))
            if -90 <= lat <= 90 and -180 <= lon <= 180 and (lat or lon):
                out[m.group(1)] = (round(lat, 4), round(lon, 4))
    return out


class FormGroups(html.parser.HTMLParser):
    """REEF species-form reference page: <b>Group</b> then 'Common name - <i>Scientific</i>' per species."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.group, self._b, self._i, self._text = [], None, None, None, []
    def handle_starttag(self, tag, attrs):
        if tag in ("b", "strong"):
            self._b = []
        elif tag == "i" and self.group:
            self._i = []
    def handle_endtag(self, tag):
        if tag in ("b", "strong") and self._b is not None:
            name = " ".join("".join(self._b).split())
            self._b = None
            # skip page titles (all caps) and the link to the invertebrate list
            if name and not name.isupper() and "species list" not in name.lower():
                self.group, self._text = name, []
        elif tag == "i" and self._i is not None:
            sci = " ".join("".join(self._i).split()).strip(" -")
            common = " ".join("".join(self._text).split()).strip(" -")
            common = re.sub(r"\s*-\s*", "-", common)          # "Black - And - Yellow Rockfish" -> "Black-And-Yellow Rockfish"
            common = re.sub(r"(?<=[a-z])-(?=[A-Z][a-z]+$)", " ", common) if common.count("-") == 1 and " " not in common else common
            if sci and common:
                self.rows.append((self.group, common, sci))
            self._i, self._text = None, []
    def handle_data(self, data):
        if self._b is not None:
            self._b.append(data)
        elif self._i is not None:
            self._i.append(data)
        elif self.group:
            self._text.append(data)


class Text(html.parser.HTMLParser):
    """Page text with a line break at every block element."""
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "td", "section"}
    def __init__(self):
        super().__init__(convert_charrefs=True); self.out = []
    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK: self.out.append("\n")
    def handle_endtag(self, tag):
        if tag in self.BLOCK: self.out.append("\n")
    def handle_data(self, data):
        self.out.append(data)


def reef_habitats():
    """REEF's habitat choices per REEF region, from its survey metadata page: {"TWA": [...], "PAC": [...], ...}."""
    p = Text(); p.feed(get("/vfsp-metadata-descriptions"))
    lines = [" ".join(l.split()) for l in "".join(p.out).splitlines()]
    lines = [l for l in lines if l]
    try:
        start = next(i for i, l in enumerate(lines) if l.lower().startswith("habitat options by region"))
    except StopIteration:
        return {}
    out, cur = {}, None
    for l in lines[start + 1:]:
        m = re.match(r"^(TWA|PAC|HAW|TEP|SOP|NE|SAS|CIP|EAM|IORS)\b(\s*\(.*\))?$", l)
        if m:
            cur = m.group(1); out.setdefault(cur, []); continue
        if cur is None:
            continue
        name = re.split(r"\s+(?:is|are|consists|includes|refers)\b", l, maxsplit=1)[0]
        name = re.sub(r"\s*\([^)]*\)", "", name).strip(" .")
        if not name or len(name) > 60 or name == l:      # not a "<Habitat> is …" line: section is over
            if out.get(cur): cur = None
            continue
        if name not in out[cur]:
            out[cur].append(name)
    return {k: v for k, v in out.items() if len(v) >= 3}


def form_groups(cfg):
    p = FormGroups()
    p.feed(get(f"{DATA}/data/data/{cfg['form_page']}"))
    return p.rows


def update_region(region, cfg, all_species, today, full=False, habitats=None):
    out = SRC / region
    out.mkdir(parents=True, exist_ok=True)
    reef = cfg["reef"]
    print(f"== {region} (REEF {reef}) ==", flush=True)

    # Sanity checks: a list that shrinks a lot since last time is probably a broken page, not real data.
    zones = zone_list(reef, cfg["prefixes"])
    if len(zones) < max(10, 0.8 * line_count(out / "sites.txt")):
        sys.exit(f"{region} zone list looks wrong ({len(zones)} rows); not updating.")
    names = dict(zones)

    sp = all_species[reef]
    if len(sp) < max(20, 0.8 * line_count(out / "species.txt")):
        sys.exit(f"{region} species list looks wrong ({len(sp)} rows); not updating.")
    own_sci = {x[2].lower() for x in sp}
    own_names = {x[1].lower() for x in sp}
    unl = {}
    for r in ALL_REGIONS:
        if r == reef:
            continue
        for code, name, sci, fam, *_ in all_species[r]:
            k = sci.lower()
            if k in own_sci or name.lower() in own_names:
                continue
            if k not in unl:
                unl[k] = [name, sci, fam, [r]]
            elif r not in unl[k][3]:
                unl[k][3].append(r)

    # Survey counts for every zone, from the big-area reports
    # Top-level areas: the configured prefixes, or the region's one-digit zones.
    tops = cfg["prefixes"] or [z for z, _ in zones if len(z) == 1]
    counts, lines = {}, {}
    for top in tops:
        print(f"  area {top} ({names.get(top, '')})…", flush=True)
        c, top_sp = geo_report(reef, top, today)
        counts.update(c)
        if top in c and top_sp:
            lines[top] = freq_line(top, c[top], top_sp)
    old = {} if full else read_old_freq(out / "freq.txt")
    eligible = [z for z, _ in zones if counts.get(z, 0) >= MIN_SURVEYS and z not in lines]
    wanted, kept = [], 0
    for z in eligible:
        if z in old and old[z][0] == counts[z]:
            lines[z] = old[z][1]          # no new surveys since last time: keep it
            kept += 1
        else:
            wanted.append(z)
    print(f"  {len(eligible)} zones with {MIN_SURVEYS}+ surveys: {kept} unchanged, {len(wanted)} to fetch"
          + (" (full refresh)" if full else ""), flush=True)
    failed = 0
    for i, z in enumerate(wanted, 1):
        try:
            _, zsp = geo_report(reef, z, today)
            if zsp:
                lines[z] = freq_line(z, counts[z], zsp)
        except Exception as e:
            failed += 1
            if z in old:
                lines[z] = old[z][1]      # keep last month's data rather than losing the site
            print(f"  {z} failed: {e}", file=sys.stderr, flush=True)
        if i % 100 == 0:
            print(f"  {i}/{len(wanted)}", flush=True)
    if failed > max(10, len(wanted) * 0.1):
        sys.exit(f"{region}: {failed} site reports failed; not updating.")

    # Site locations and REEF form groups (small; refreshed every run). Keep the old file if a fetch fails.
    try:
        coords = site_coords(cfg, tops)
        if len(coords) > len(zones) * 0.3:
            (out / "coords.txt").write_text("\n".join(f"{z}|{la}|{lo}" for z, (la, lo) in sorted(coords.items())) + "\n")
        print(f"  {len(coords)} sites with coordinates", flush=True)
    except Exception as e:
        print(f"  coordinates failed: {e}", file=sys.stderr, flush=True)
    try:
        groups = form_groups(cfg)
        if len(groups) > 50:
            (out / "form_groups.txt").write_text("\n".join("|".join(map(clean, g)) for g in groups) + "\n")
        print(f"  {len(groups)} species in {len({g[0] for g in groups})} REEF form groups", flush=True)
    except Exception as e:
        print(f"  form groups failed: {e}", file=sys.stderr, flush=True)

    if habitats and habitats.get(reef):
        (out / "habitats.txt").write_text("\n".join(habitats[reef]) + "\n")

    (out / "sites.txt").write_text("\n".join(f"{c}|{n}" for c, n in zones) + "\n")
    (out / "species.txt").write_text("\n".join("|".join(x) for x in sp) + "\n")
    rows = sorted(unl.values(), key=lambda x: x[0].lower())
    (out / "unlisted.txt").write_text("\n".join(f"{a}|{b}|{c}|{','.join(d)}" for a, b, c, d in rows) + "\n")
    order = {z: i for i, (z, _) in enumerate(zones)}
    (out / "freq.txt").write_text("\n".join(lines[z] for z in sorted(lines, key=lambda z: order.get(z, 0)) if lines[z]) + "\n")
    print(f"  {len(zones)} zones, {len(sp)} species, {len(rows)} other-region species, "
          f"{sum(1 for v in lines.values() if v)} zones with history", flush=True)


def main():
    today = datetime.date.today().isoformat()
    regions = load_regions()
    args = sys.argv[1:]
    full = "--full" in args
    wanted = [r for r in args if r in regions] or list(regions)
    print("Species lists for all regions…", flush=True)
    all_species = {r: species(r) for r in ALL_REGIONS}
    try:
        habitats = reef_habitats()
        print(f"Habitat lists for {', '.join(habitats) or 'no regions'}", flush=True)
    except Exception as e:
        habitats = {}
        print(f"Habitat lists failed: {e}", file=sys.stderr, flush=True)
    for region in wanted:
        update_region(region, regions[region], all_species, today, full=full, habitats=habitats)
    (SRC / "data_date.txt").write_text(today + "\n")
    print("Done.", flush=True)


if __name__ == "__main__":
    main()
