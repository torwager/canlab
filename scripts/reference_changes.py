"""Write updated_references.txt: what changed in each reference compared with the previous data/papers.json (git HEAD)."""
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
old = {p["id"]: p for p in json.loads(subprocess.run(["git", "show", "HEAD:data/papers.json"], capture_output=True, text=True, cwd=ROOT).stdout)}
new = json.load(open(ROOT / "data" / "papers.json"))
lines = ["Reference updates, 2026-09-07", "=" * 28, "",
         "Every citation was regenerated in one style (Authors (Year). Title. Journal, Volume(Issue), Pages. DOI) from structured fields;",
         "journal names were normalized (e.g. Neuroimage -> NeuroImage, PAIN -> Pain, 'The' and empty names filled from the original citation);",
         "publisher details were filled from Crossref by DOI, DOIs were validated against Crossref titles, and PDFs now live in site/pdf/.", ""]
n_new = n_meta = n_pdf = 0
FIELDS = ("journal", "volume", "issue", "pages", "doi", "year", "kind", "title")
for p in new:
    o = old.get(p["id"])
    ch = []
    if not o:
        n_new += 1; lines.append(f"[NEW] {p['citation']}"); continue
    for f in FIELDS:
        a, b = (o.get(f) or ""), (p.get(f) or "")
        if str(a) != str(b) and b:
            ch.append(f"{f}: '{a}' -> '{b}'" if a else f"{f} added: '{b}'")
    if not o.get("abstract") and p.get("abstract"):
        ch.append(f"abstract added ({p.get('abstract_source', 'crossref')})")
    op = next((l for l in o.get("links", []) if l["type"] == "pdf"), None); np_ = next((l for l in p.get("links", []) if l["type"] == "pdf"), None)
    if np_ and not op:
        ch.append("PDF added"); n_pdf += 1
    elif np_ and op and np_.get("version") == "publisher" and ("author_manuscript" in (op.get("url") or "") or o["id"] in json.load(open(ROOT / "work" / "pdf_status.json"))["author_manuscripts"] and False):
        pass
    if np_ and np_.get("version") == "author_manuscript":
        ch.append("PDF is the PubMed author manuscript (publisher version not freely available)")
    if any(l["type"] == "maps" for l in p["links"]) and not any(l["type"] == "maps" for l in o.get("links", [])):
        ch.append("link to Neuroimaging_Pattern_Masks added")
    if p.get("commentaries") and not o.get("commentaries"):
        ch.append("commentary/editorial attached: " + "; ".join(c["title"] for c in p["commentaries"]))
    if ch:
        n_meta += 1; lines.append(f"{p['id']}: " + "; ".join(ch))
removed = [i for i in old if i not in {p["id"] for p in new}]
lines += ["", f"Removed from the list (not Wager-authored, or merged): {', '.join(removed)}", "",
          f"Summary: {n_new} new records (from the CV), {n_meta} records with updated details, {n_pdf} newly added PDFs."]
(ROOT / "updated_references.txt").write_text("\n".join(lines))
print(lines[-1])
