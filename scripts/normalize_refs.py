"""Normalize journal names and regenerate every citation in one style (APA-like), writing a change log to updated_references.txt.

Style: Authors (Year). Title. Journal, Volume(Issue), Pages. https://doi.org/DOI
Chapters: Authors (Year). Title. In Book/Editors. Pages.   Preprints: Authors (Year). Title. bioRxiv. https://doi.org/DOI
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
papers = json.load(open(ROOT / "data" / "papers.json"))

sys.path.insert(0, str(ROOT))
from pipeline.refs import JOURNALS, journal_from_citation, canon, authors_line, pages_str, make_citation  # noqa: E402,F401


log = []
for r in papers:
    old_j, old_c = r.get("journal") or "", r.get("citation") or ""
    r["journal"] = canon(old_j, r)
    r["citation_original"] = r.get("citation_original") or old_c
    r["citation"] = make_citation(r)
    changes = []
    if r["journal"] != old_j:
        changes.append(f"journal: '{old_j}' -> '{r['journal']}'")
    if r["citation"] != old_c:
        changes.append("citation restyled")
    if changes:
        log.append(f"{r['id']}: " + "; ".join(changes))
json.dump(papers, open(ROOT / "data" / "papers.json", "w"), indent=1, ensure_ascii=False)
print(len(log), "records changed")
