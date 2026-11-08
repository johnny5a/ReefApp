"""Build index.html from src/: python3 build.py
Inlines the species list and California zone codes into the app page.
After building, bump VERSION in sw.js so phones pick up the change."""
from pathlib import Path
src = Path(__file__).parent / "src"
page = (src / "index.src.html").read_text()
species = (src / "species_pac.txt").read_text().strip()
sites = (src / "sites_ca.txt").read_text().strip()
for name, text in (("species", species), ("sites", sites)):
    assert "`" not in text and "${" not in text, f"{name} list has characters that break the page"
out = page.replace("/*SPECIES*/", species).replace("/*SITES*/", sites)
(Path(__file__).parent / "index.html").write_text(out)
print("index.html built")
