"""Build index.html from src/: python3 build.py
Inlines the PAC species list, other-region (unlisted) species and California zone codes into the app page.
After building, bump VERSION in sw.js so phones pick up the change."""
from pathlib import Path
src = Path(__file__).parent / "src"
page = (src / "index.src.html").read_text()
species = (src / "species_pac.txt").read_text().strip()
sites = (src / "sites_ca.txt").read_text().strip()
unl_file = src / "species_unlisted.txt"
unlisted = unl_file.read_text().strip() if unl_file.exists() else ""
date_file = src / "data_date.txt"
data_date = date_file.read_text().strip() if date_file.exists() else ""
freq_file = src / "site_freq_ca.txt"
sitefreq = freq_file.read_text().strip() if freq_file.exists() else ""
for name, text in (("species", species), ("sites", sites), ("unlisted", unlisted), ("site frequencies", sitefreq)):
    assert "`" not in text and "${" not in text, f"{name} list has characters that break the page"
out = page.replace("/*SPECIES*/", species).replace("/*SITES*/", sites).replace("/*UNLISTED*/", unlisted).replace("/*SITEFREQ*/", sitefreq).replace("/*DATADATE*/", data_date)
(Path(__file__).parent / "index.html").write_text(out)
print("index.html built")
