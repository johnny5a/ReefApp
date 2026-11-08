"""Refresh the REEF data the app ships with, straight from reef.org.

Writes into src/:
  sites_ca.txt          California Geographic Zone Codes      code|name
  species_pac.txt       PAC species list (REEF codes)          code|common|scientific|family
  species_unlisted.txt  Species from REEF's other regions      common|scientific|family|regions
  site_freq_ca.txt      How often each species is seen per     zone|surveys|code:pct,code:pct,...
                        California site/area (Geographic Zone Report, total SF%)
  data_date.txt         Date of this refresh

Run:  python3 scripts/update_reef_data.py   (then python3 build.py)
Uses only the standard library. Requests are sequential with a pause, to be gentle on reef.org.
"""
import datetime, html.parser, sys, time, urllib.parse, urllib.request
from pathlib import Path

BASE = "https://www.reef.org"
SRC = Path(__file__).resolve().parent.parent / "src"
UA = "ReefApp data updater (https://github.com/johnny5a/ReefApp)"
PAUSE = 0.4  # seconds between requests
REGIONS = ["TWA", "PAC", "HAW", "TEP", "SOP", "NE", "SAS", "CIP", "EAM", "IORS"]


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


def get(path, tries=3):
    url = path if path.startswith("http") else BASE + path
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                text = r.read().decode("utf-8", "replace")
            time.sleep(PAUSE)
            return text
        except Exception as e:  # network hiccup: back off and retry
            if attempt == tries - 1:
                raise
            print(f"  retry {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))


def tables(path):
    p = Tables()
    p.feed(get(path))
    return p.tables


def clean(s):
    return " ".join(str(s).replace("|", "/").replace("`", "'").replace("${", "$ {").split())


def zone_list():
    rows = [r for t in tables("/db/zonecodes/list/?region_code=PAC") for r in t]
    # columns: Zone | Zone Code list | Geographic Report | Name | Have Coordinates?
    out = [(r[0], clean(r[3])) for r in rows if len(r) >= 4 and r[0].isdigit() and r[0].startswith("4")]
    if len(out) < 500:
        sys.exit(f"Zone list looks wrong ({len(out)} California rows); not updating.")
    return out


def species(region):
    rows = [r for t in tables(f"/db/reports/species?region_code={region}") for r in t]
    # columns: Image | Species ID | Common | Scientific | Family common | Family scientific
    return [(r[1], clean(r[2]), clean(r[3]), clean(r[5])) for r in rows
            if len(r) >= 6 and r[1].isdigit() and 3 <= len(r[1]) <= 5]


def site_freq(zone, today):
    q = urllib.parse.urlencode({"end_date": today, "format_type": "table", "group_type": "species",
                                "language": "common", "region_code": "PAC", "start_date": "1993-01-01", "zones": zone})
    ts = tables("/db/reports/geo?" + q)
    if len(ts) < 2:
        return 0, []
    # Table 0: survey counts; the zone's own row is Code | Name | 6 survey-count columns | bottom time
    own = next((r for r in ts[0] if r and r[0] == zone), None)
    n = sum(int(x.replace(",", "") or 0) for x in own[2:8] if x.replace(",", "").isdigit()) if own else 0
    # Table 1: Rank | Species ID | Species | Family | SF% | DEN | ...
    sp = []
    for r in ts[1]:
        if len(r) >= 5 and r[0].isdigit():
            try:
                sp.append((r[1], round(float(r[4]))))
            except ValueError:
                pass
    return n, sp


def main():
    today = datetime.date.today().isoformat()
    SRC.mkdir(exist_ok=True)

    print("Zone codes…")
    zones = zone_list()
    (SRC / "sites_ca.txt").write_text("\n".join(f"{c}|{n}" for c, n in zones) + "\n")
    print(f"  {len(zones)} California zones")

    print("Species lists…")
    by_region = {r: species(r) for r in REGIONS}
    pac = by_region["PAC"]
    if len(pac) < 400:
        sys.exit(f"PAC species list looks wrong ({len(pac)} rows); not updating.")
    (SRC / "species_pac.txt").write_text("\n".join("|".join(x) for x in pac) + "\n")
    pac_sci = {x[2].lower() for x in pac}
    unl = {}
    for r in REGIONS:
        if r == "PAC":
            continue
        for code, name, sci, fam in by_region[r]:
            k = sci.lower()
            if k in pac_sci:
                continue
            if k not in unl:
                unl[k] = [name, sci, fam, [r]]
            elif r not in unl[k][3]:
                unl[k][3].append(r)
    unl_rows = sorted(unl.values(), key=lambda x: x[0].lower())
    (SRC / "species_unlisted.txt").write_text("\n".join(f"{a}|{b}|{c}|{','.join(d)}" for a, b, c, d in unl_rows) + "\n")
    print(f"  {len(pac)} PAC species, {len(unl_rows)} from other regions")

    print("Site species frequencies (one report per site; this takes a while)…")
    codes = [c for c, n in zones if len(c) >= 2 and not n.lower().startswith("please use")]
    lines, failed = [], 0
    for i, c in enumerate(codes, 1):
        try:
            n, sp = site_freq(c, today)
        except Exception as e:
            failed += 1
            print(f"  {c} failed: {e}", file=sys.stderr)
            continue
        if n > 0 and sp:
            lines.append(f"{c}|{n}|" + ",".join(f"{code}:{p}" for code, p in sp))
        if i % 50 == 0:
            print(f"  {i}/{len(codes)}")
    if failed > len(codes) * 0.1:
        sys.exit(f"{failed} site reports failed; not updating site frequencies.")
    (SRC / "site_freq_ca.txt").write_text("\n".join(lines) + "\n")
    print(f"  {len(lines)} sites/areas with survey history")

    (SRC / "data_date.txt").write_text(today + "\n")
    print("Done.")


if __name__ == "__main__":
    main()
