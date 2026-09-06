"""One-time import of the publication list from sites.dartmouth.edu/canlab into data/papers.json.

Inputs (produced by the scraping scripts in scripts/scrape/, kept for provenance):
  papers_parsed.json     parsed citations + typed links from the Dartmouth publications page
  openalex_cache.json    OpenAlex matches (DOI, PMID, abstract, full author list, citation counts)
  pdf_map.json           original PDF URL -> local file name (mirrored to the GitHub release 'pdfs')
Existing tags/summaries in data/papers.json are preserved when re-run.
"""
import json, re, sys, unicodedata
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "work" / "dartmouth"
OUT = ROOT / "data" / "papers.json"
RELEASE_BASE = "https://github.com/torwager/canlab/releases/download/pdfs/"

parsed = json.load(open(SRC / "papers_parsed.json"))
oa = json.load(open(SRC / "openalex_cache.json"))
cr = json.load(open(SRC / "crossref_cache.json")) if (SRC / "crossref_cache.json").exists() else {}
pdfmap = json.load(open(SRC / "pdf_map.json"))
# links on the old page that pointed at the wrong file (verified by reading the PDF text)
WRONG_PDF = {"calhoun2017impact": "2019_12_2017_de-la-Vega_CerebCortex.pdf", "schafer2015partial": "2019_12_2015_Schafer_Psychosom-Med.pdf"}
old = {}
if OUT.exists():
    old = {r["id"]: r for r in json.load(open(OUT))}

def clean_name(a):
    """'Wager, T. D' -> 'Wager, T. D.'; 'Zhang, L.-B' -> 'Zhang, L.-B.'; consortium names unchanged."""
    a = re.sub(r"\s+", " ", a).strip(" .,")
    if "consortium" in a.lower() or "," not in a:
        return re.sub(r"^(the )", "", a, flags=re.I) if "consortium" in a.lower() else a
    sur, given = a.split(",", 1)
    given = re.sub(r"\b([A-Z])(?![a-z.])", r"\1.", given.strip())   # add a period after each bare initial
    given = given.replace("..", ".")
    return f"{sur.strip()}, {given}"

def surname_initials(a):
    """'Wager, T. D.' -> 'Wager TD'; 'Placebo Imaging Consortium' unchanged."""
    if "," in a:
        s, g = a.split(",", 1)
        return (s.strip() + " " + "".join(ch for ch in g if ch.isalpha() and ch.isupper())).strip()
    return a

papers = []
for it in parsed:
    m = oa.get(it["id"]) or {}
    matched = bool(m) and not m.get("nomatch")
    c = cr.get(it["id"]) or {}
    if not matched and c.get("doi"):
        # Crossref + PubMed fallback, mapped onto the OpenAlex-shaped fields used below
        m = {"doi": c["doi"], "pmid": c.get("pmid"), "pmcid": c.get("pmcid"), "journal": c.get("journal"), "volume": c.get("volume"), "issue": c.get("issue"),
             "first_page": (c.get("pages") or "").split("-")[0] or None, "last_page": (c.get("pages") or "").split("-")[-1] if "-" in (c.get("pages") or "") else None,
             "year": c.get("year"), "date": None, "abstract": c.get("abstract") or "", "cited_by_count": c.get("cited_by_count"), "authors": c.get("authors") or [],
             "landing_url": c.get("landing_url"), "keywords": [], "openalex": None}
        matched = True
    elif matched and not m.get("abstract") and c.get("abstract"):
        m["abstract"] = c["abstract"]
        if not m.get("pmid") and c.get("pmid"):
            m["pmid"] = c["pmid"]
    links = []
    pdf = None
    for L in it["links"]:
        u = L["url"]
        if "safelinks.protection.outlook.com" in u:
            mm = re.search(r"url=([^&]+)", u)
            if mm:
                import urllib.parse
                u = urllib.parse.unquote(mm.group(1))
        rec = {"type": L["type"], "label": re.sub(r"^[\[\s,]+|[\]\s,]+$", "", L["label"]) or L["type"], "url": u}
        if L["type"] == "pdf" and "sites.dartmouth.edu" in u and u in pdfmap:
            if WRONG_PDF.get(it["id"]) == pdfmap[u]:
                continue
            rec["file"] = pdfmap[u]
            rec["mirror"] = RELEASE_BASE + pdfmap[u]
            if pdf is None:
                pdf = rec
        links.append(rec)
    authors = [clean_name(a) for a in it["authors"]]
    rec = {
        "id": it["id"],
        "title": it["title"],
        "authors": authors,
        "authors_short": [surname_initials(a) for a in authors],
        "year": it["year"],
        "status": it["status"],
        "kind": it.get("kind", "article"),
        "journal": it["journal"] or (m.get("journal") or ""),
        "volume": it.get("volume") or m.get("volume"),
        "issue": m.get("issue"),
        "pages": it.get("pages") or (f"{m.get('first_page')}-{m.get('last_page')}" if m.get("first_page") and m.get("last_page") else m.get("first_page")),
        "citation": it["citation"],
        "doi": (m.get("doi") or "").lower() or None,
        "pmid": m.get("pmid") or None,
        "pmcid": m.get("pmcid") or None,
        "openalex_id": (m.get("openalex") or None) if matched else None,
        "date": m.get("date") if matched and m.get("year") == it["year"] else None,
        "abstract": m.get("abstract") or "",
        "cited_by_count": m.get("cited_by_count") if matched else None,
        "oa_status": m.get("oa_status") if matched else None,
        "oa_url": m.get("oa_url") if matched else None,
        "landing_url": m.get("landing_url") if matched else None,
        "openalex_authors": [a["name"] for a in m.get("authors", [])] if matched else [],
        "keywords": (m.get("keywords") or []) if matched else [],
        "links": links,
        "has_pdf": pdf is not None,
        "section": it["section"],
        "source": "dartmouth-site",
        "date_added": "2026-09-06",
    }
    # DOI from links when OpenAlex missed it
    if not rec["doi"]:
        for L in links:
            mm = re.search(r"doi\.org/(10\.\S+)", L["url"])
            if mm:
                rec["doi"] = mm.group(1).rstrip("/").lower(); break
    o = old.get(it["id"])
    if o:
        for k in ("tags", "summary", "key_finding", "free_keywords", "classification", "featured", "notes"):
            if k in o:
                rec[k] = o[k]
    papers.append(rec)
# the old page listed a few papers twice: keep the first, merge any extra links
seen = {}
deduped = []
for r in papers:
    key = re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", r["title"]).encode("ascii", "ignore").decode().lower()).strip()
    if key in seen and abs((seen[key].get("year") or 0) - (r.get("year") or 0)) <= 1:
        first = seen[key]
        for L in r["links"]:
            if L["url"] not in {x["url"] for x in first["links"]}:
                first["links"].append(L)
        first["has_pdf"] = any(l["type"] == "pdf" for l in first["links"])
        print("merged duplicate:", r["id"], "->", first["id"])
        continue
    seen[key] = r
    deduped.append(r)
papers = deduped
json.dump(papers, open(OUT, "w"), indent=1, ensure_ascii=False)
print(len(papers), "papers ->", OUT)
print("doi", sum(1 for p in papers if p["doi"]), "abstract", sum(1 for p in papers if p["abstract"]), "pdf", sum(1 for p in papers if p["has_pdf"]), "cites", sum(1 for p in papers if p["cited_by_count"] is not None))
