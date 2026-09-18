"""Audit every paper's DOI: does the DOI's Crossref record match the paper we think it is?

Flags a record when the Crossref title differs, when the DOI is a book chapter/component but the paper is
an article (the NEJM pain-signature paper had been matched to a same-titled chapter in a book summarising
it), when the journal in the old site's citation differs from Crossref's container, or when the year is off.
For flagged records it proposes a replacement DOI from the PMID in the original citation (PubMed) or from a
Crossref bibliographic search, validated by title similarity. Writes work/doi_audit.json.

    python scripts/audit_dois.py            # audit only
    python scripts/audit_dois.py --apply    # also write validated replacements into data/papers.json
"""
import argparse
import difflib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "canlab-site-audit/1.0 (https://github.com/torwager/canlab)"}


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:
            time.sleep(2 * (i + 1))
    return None


def norm(t):
    t = re.sub(r"<[^>]+>", "", t or "").lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def orig_journal(c):
    """Journal named in the old site's citation: the text after the title's full stop, before volume/year."""
    m = re.search(r"\(\d{4}[a-z]?\)\.\s*(.+?)\.\s+(.+?)(?:[.,]\s*\d|\.\s*PMID|\.\s*\[|$)", c or "")
    return m.group(2).strip() if m else ""


def orig_pmid(c):
    m = re.search(r"PMID:?\s*(\d{6,9})", c or "")
    return m.group(1) if m else None


def pubmed_doi(pmid):
    d = get(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={pmid}&retmode=json")
    try:
        rec = d["result"][pmid]
    except (TypeError, KeyError):
        return None, None
    doi = next((a["value"] for a in rec.get("articleids", []) if a["idtype"] == "doi"), None)
    return doi, rec.get("title")


def crossref(doi):
    d = get("https://api.crossref.org/works/" + urllib.parse.quote(doi))
    return d and d.get("message")


def search(title, author, journal):
    q = urllib.parse.urlencode({"query.bibliographic": f"{title} {journal}", "query.author": author, "rows": 5, "select": "DOI,title,container-title,type,issued,is-referenced-by-count"})
    d = get("https://api.crossref.org/works?" + q)
    return (d or {}).get("message", {}).get("items", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    papers = json.loads((ROOT / "data" / "papers.json").read_text())
    out = []
    for n, p in enumerate(papers, 1):
        if a.only and p["id"] != a.only:
            continue
        if p.get("kind") in ("chapter",) or p.get("status") == "preprint":
            continue
        oc = p.get("citation_original") or ""
        oj, opm = orig_journal(oc), orig_pmid(oc)
        issues, cr = [], None
        if p.get("doi"):
            cr = crossref(p["doi"])
            time.sleep(0.2)
            if not cr:
                issues.append("doi not in Crossref")
            else:
                ct = (cr.get("title") or [""])[0]
                cc = (cr.get("container-title") or [""])[0]
                cy = ((cr.get("issued") or {}).get("date-parts") or [[None]])[0][0]
                if sim(ct, p["title"]) < 0.85:
                    issues.append(f"title differs: {ct[:80]!r}")
                if cr.get("type") in ("book-chapter", "component", "reference-entry", "book") and p.get("kind") == "article":
                    issues.append(f"doi is a {cr.get('type')} in {cc!r}")
                if oj and cc and sim(oj, cc) < 0.5 and norm(oj) not in norm(cc) and norm(cc) not in norm(oj):
                    issues.append(f"journal: old site {oj!r} vs Crossref {cc!r}")
                if cy and p.get("year") and abs(int(cy) - int(p["year"])) > 1:
                    issues.append(f"year {p['year']} vs Crossref {cy}")
        else:
            issues.append("no doi")
        if opm and p.get("pmid") and str(p["pmid"]) != opm:
            issues.append(f"pmid {p['pmid']} vs old site {opm}")
        if not issues:
            continue
        fix = None
        if opm:
            doi, t = pubmed_doi(opm)
            time.sleep(0.4)
            if doi and sim(t, p["title"]) >= 0.8:
                fix = {"doi": doi.lower(), "pmid": opm, "via": "pubmed", "title": t}
        if not fix:
            first = (p.get("authors") or [""])[0].split(",")[0]
            for it in search(p["title"], first, oj):
                t = (it.get("title") or [""])[0]
                if sim(t, p["title"]) >= 0.9 and it.get("type") == "journal-article":
                    cc = (it.get("container-title") or [""])[0]
                    if oj and sim(oj, cc) < 0.5 and norm(oj) not in norm(cc) and norm(cc) not in norm(oj):
                        continue
                    fix = {"doi": it["DOI"].lower(), "via": "crossref-search", "title": t, "journal": cc}
                    break
            time.sleep(0.3)
        if fix and fix["doi"] == (p.get("doi") or "").lower():
            fix = None
        out.append({"id": p["id"], "title": p["title"], "year": p.get("year"), "doi": p.get("doi"), "journal": p.get("journal"),
                    "orig_journal": oj, "orig_pmid": opm, "cited_by_count": p.get("cited_by_count"), "issues": issues, "fix": fix})
        print(f"{n}/{len(papers)} {p['id']}: {'; '.join(issues)}" + (f"  -> {fix['doi']} ({fix['via']})" if fix else ""), flush=True)
    (ROOT / "work").mkdir(exist_ok=True)
    (ROOT / "work" / "doi_audit.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"{len(out)} flagged, {sum(1 for o in out if o['fix'])} with a proposed fix -> work/doi_audit.json")


if __name__ == "__main__":
    main()
