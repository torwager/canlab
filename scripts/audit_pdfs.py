"""Audit every PDF linked from data/papers.json: is it really the published paper?

Checks, from the text of the first two pages (PyMuPDF):
  - the title appears (pipeline.fetch_pdfs.matches_title);
  - the first author's surname appears;
  - no DOI on page 1 that belongs to a different paper (DOIs of other papers on page 1 mean a different article);
  - it is not paperwork: licence/copyright forms, cover letters, reviewer responses, supplements, proofs to approve;
  - page count is plausible (articles >= 3 pages; commentaries, letters and replies may be shorter).
Scanned PDFs without a text layer cannot be checked and are listed separately.
Writes work/pdf_audit.json and prints one line per problem. Usage: python scripts/audit_pdfs.py [--ids a,b]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pymupdf  # noqa: E402

from pipeline.fetch_pdfs import matches_title, norm  # noqa: E402

PAPERWORK = re.compile(r"licen[cs]e to publish|copyright transfer|transfer of copyright|author(?:'s)? (?:publishing )?agreement|"
                       r"exclusive licen[cs]e|consent to publish|dear (?:dr\.?|prof\.?|editor)|cover letter|response to (?:the )?reviewers|"
                       r"reviewer #?\d|manuscript number|^\s*supplementa(?:ry|l) (?:material|information|methods)|"
                       r"page \d+ of \d+\s+licen|proof(?:s)? for (?:your )?approval|author query", re.I | re.M)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>()\[\]]+", re.I)
SHORT_OK = re.compile(r"reply|response|comment|letter|editorial|correction|erratum|preface|introduction to|commentary|perspective|news", re.I)


def surname(p):
    a = (p.get("authors") or [""])[0]
    return norm(a.split(",")[0]).split()[-1] if a and "," in a else ""


def check(p):
    link = next(l for l in p["links"] if l["type"] == "pdf")
    url = link["url"]
    if url.startswith("http"):
        return {"status": "external", "reasons": [f"external PDF link {url}"]}
    path = ROOT / "site" / url
    if not path.exists():
        return {"status": "fail", "reasons": ["file missing"]}
    data = path.read_bytes()
    try:
        d = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return {"status": "fail", "reasons": ["not a readable PDF"]}
    p1 = d[0].get_text() if d.page_count else ""
    text = "\n".join(d[i].get_text() for i in range(min(2, d.page_count)))
    if len(norm(text)) < 200:
        return {"status": "scanned", "reasons": ["no text layer (scanned); not checkable"], "pages": d.page_count}
    reasons = []
    if not matches_title(data, p["title"]):
        reasons.append("title not on first pages")
    sn = surname(p)
    if sn and len(sn) > 2 and sn not in norm(text).split() and sn not in norm(text):
        reasons.append(f"first author '{sn}' not on first pages")
    if PAPERWORK.search(p1):
        reasons.append("looks like paperwork: " + PAPERWORK.search(p1).group(0).strip()[:40])
    if p.get("doi"):
        dois = {m.rstrip(".,;").lower() for m in DOI_RE.findall(p1)}
        mine = p["doi"].lower()
        others = {x for x in dois if not (x.startswith(mine) or mine.startswith(x))}
        if dois and not any(x.startswith(mine) or mine.startswith(x) for x in dois) and others:
            reasons.append("page-1 DOI(s) of another paper: " + ", ".join(sorted(others))[:120])
    if d.page_count < 3 and p.get("kind") == "article" and not SHORT_OK.search(p["title"] + " " + (p.get("journal") or "")):
        reasons.append(f"only {d.page_count} page(s)")
    return {"status": "problem" if reasons else "ok", "reasons": reasons, "pages": d.page_count,
            "first_page": " ".join(p1.split())[:220]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids")
    a = ap.parse_args()
    papers = json.loads((ROOT / "data" / "papers.json").read_text())
    ids = set(a.ids.split(",")) if a.ids else None
    out = {}
    for p in papers:
        if (ids and p["id"] not in ids) or not any(l["type"] == "pdf" for l in p.get("links", [])):
            continue
        r = check(p)
        out[p["id"]] = r
        if r["status"] != "ok":
            print(f"{r['status'].upper():9} {p['id']}: {'; '.join(r['reasons'])}")
    (ROOT / "work").mkdir(exist_ok=True)
    (ROOT / "work" / "pdf_audit.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    from collections import Counter
    print(Counter(r["status"] for r in out.values()))


if __name__ == "__main__":
    main()
