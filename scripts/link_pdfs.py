"""Point every paper's PDF link at the copy in site/pdf/ (final version) or site/pdf/author_manuscripts/ (PubMed author manuscript)."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
papers = json.load(open(ROOT / "data" / "papers.json"))
n_final = n_am = n_none = 0
for p in papers:
    final = ROOT / "site" / "pdf" / f"{p['id']}.pdf"
    am = ROOT / "site" / "pdf" / "author_manuscripts" / f"{p['id']}.pdf"
    old = next((l for l in p["links"] if l["type"] == "pdf"), None)
    p["links"] = [l for l in p["links"] if l["type"] != "pdf"]
    if final.exists():
        p["links"].insert(0, {"type": "pdf", "label": "PDF", "url": f"pdf/{p['id']}.pdf", "url_original": (old or {}).get("url_original") or (old or {}).get("url"), "version": "publisher"})
        p["has_pdf"] = True; n_final += 1
    elif am.exists():
        p["links"].insert(0, {"type": "pdf", "label": "PDF (author manuscript)", "url": f"pdf/author_manuscripts/{p['id']}.pdf", "url_original": (old or {}).get("url_original") or (old or {}).get("url"), "version": "author_manuscript"})
        p["has_pdf"] = True; n_am += 1
    else:
        p["has_pdf"] = False; n_none += 1
json.dump(papers, open(ROOT / "data" / "papers.json", "w"), indent=1, ensure_ascii=False)
print(f"linked {n_final} publisher PDFs, {n_am} author manuscripts, {n_none} without PDF")
