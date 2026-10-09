"""Find and attach PDFs (and publisher links) for lab papers that are missing them. Runs in the daily workflow.

For every paper in data/papers.json without a PDF link:
  0. a file already saved as site/pdf/<id>.pdf (or site/pdf/author_manuscripts/<id>.pdf) is linked. This is how
     the PI adds paywalled PDFs by hand: save the file under that name and push;
  1. a missing DOI is looked up in Crossref (accepted only on a near-exact title + first-author match), which also
     gives the paper its publisher link;
  2. open-access copies are tried in order: OpenAlex locations, Unpaywall (only when CANLAB_CONTACT_EMAIL is set),
     PubMed Central (NCBI's open-data bucket on AWS), then the publisher's own page, visited the way a browser does (the article
     page first, so the site sets its session cookies, then the PDF link it advertises: citation_pdf_url,
     LWW's /pdf/ twin of /fulltext/, or a "Download PDF" link on the same site); a preprint PDF is the last resort;
  3. every candidate must really be a PDF of THIS paper: its first two pages must contain the title (>= 80% of the
     title's words, so a cited reference or a different paper is rejected). Scanned PDFs without text are skipped.
Saved as site/pdf/<id>.pdf, or site/pdf/author_manuscripts/<id>.pdf for PMC author manuscripts, and linked with
version publisher | author_manuscript | preprint. Never defeats paywalls, logins or bot challenges: a page that
answers with a challenge is simply recorded as not found.

Each attempt is recorded in paper["pdf_search"] = {last, result, tried}; papers still missing are re-tried weekly
(monthly when older than three years). reports/missing_pdfs.md lists what is left, with the publisher link to
download from (institutional access) and the file name to save it under.

Usage: python -m pipeline.fetch_pdfs [--ids a,b] [--force] [--dry-run] [--max N]
"""
import argparse
import datetime as dt
import difflib
import html as htmllib
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
from pathlib import Path

import requests

from . import config

ROOT = config.ROOT
PAPERS = ROOT / "data" / "papers.json"
PDF_DIR = ROOT / "site" / "pdf"
AM_DIR = PDF_DIR / "author_manuscripts"
REPORT = ROOT / "reports" / "missing_pdfs.md"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
API_UA = {"User-Agent": "canlab-site/1.0 (https://canlab.science; pdf finder)"}
MAX_BYTES = 60_000_000


# ---------------------------------------------------------------- helpers
def norm(t):
    t = unicodedata.normalize("NFKC", htmllib.unescape(re.sub(r"<[^>]+>", " ", t or ""))).lower()  # NFKC: "ﬁ" -> "fi"
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def has_pdf(p):
    return any(l.get("type") == "pdf" for l in p.get("links", []))


def due(p, today, force):
    if force:
        return True
    s = p.get("pdf_search") or {}
    if not s.get("last"):
        return True
    age_days = (today - dt.date.fromisoformat(s["last"])).days
    old = (p.get("year") or today.year) < today.year - 3
    return age_days >= (30 if old else 7)


def get_json(url, **kw):
    for attempt in range(3):
        try:
            r = requests.get(url, headers=API_UA, timeout=40, **kw)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def pdf_text(data, pages=2):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    try:
        d = pymupdf.open(stream=data, filetype="pdf")
        return "\n".join(d[i].get_text() for i in range(min(pages, d.page_count)))
    except Exception:
        return ""


def matches_title(data, title):
    """True when the PDF's first pages contain the paper's title (>= 80% of its significant words, in order-ish)."""
    text = norm(pdf_text(data))
    if not text:
        return False
    words = [w for w in norm(title).split() if len(w) > 3]
    if not words:
        return False
    tw = set(text.split())
    cover = sum(1 for w in words if w in tw) / len(words)
    if cover < 0.8:
        return False
    # the title should also appear as a run of text, not scattered words from a reference list
    t = norm(title)
    if t in text:
        return True
    win = len(t)
    best = max((difflib.SequenceMatcher(None, t, text[i:i + win]).ratio() for i in range(0, max(1, len(text) - win + 1), max(1, win // 4))), default=0)
    return best >= 0.72


def is_author_manuscript(data):
    t = pdf_text(data, pages=1).lower()
    return "hhs public access" in t or "author manuscript" in t


PAPERWORK = re.compile(r"licen[cs]e to publish|copyright transfer|transfer of copyright|author(?:'s)? (?:publishing )?agreement form|"
                       r"consent to publish|dear (?:dr\.?|prof\.?|editor)|cover letter|response to (?:the )?reviewers|reviewer #?\d|"
                       r"^\s*supplementa(?:ry|l) (?:material|information|methods)\b|proof(?:s)? for (?:your )?approval|author query", re.I | re.M)
AM_MARK = re.compile(r"hhs public access|author manuscript|accepted manuscript|manuscript draft|running head|first proof|"
                     r"uncorrected proof|this article has been accepted for publication|in press at", re.I)
PRE_MARK = re.compile(r"(?<!reviewed )\bpreprint\b(?!\s+posted)|\barxiv\b|biorxiv|medrxiv|psyarxiv|not peer.reviewed|^posted:", re.I | re.M)
DOI_ON_PAGE = re.compile(r"10\.\d{4,9}/[^\s\"'<>()\[\]]+", re.I)


def verify(data, p):
    """Problems that mean `data` is not this paper (empty list = acceptable). The title alone is not enough:
    a journal's licence-to-publish form carries the full title (that is how a wrong PDF got onto the site)."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    try:
        d = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return ["not a readable PDF"]
    p1 = d[0].get_text() if d.page_count else ""
    text = "\n".join(d[i].get_text() for i in range(min(2, d.page_count)))
    if len(norm(text)) < 200:
        return ["no text layer"]
    out = []
    if not matches_title(data, p["title"]):
        out.append("title not on first pages")
    m = PAPERWORK.search(p1)
    if m:
        out.append("paperwork: " + " ".join(m.group(0).split()))
    if p.get("doi"):
        mine = p["doi"].lower()
        dois = {x.rstrip(".,;").lower() for x in DOI_ON_PAGE.findall(p1.replace("\u200b", ""))}
        if dois and not any(x.startswith(mine) or mine.startswith(x) for x in dois) and not any(x.startswith(("10.1101/", "10.48550/", "10.31234/")) for x in dois):
            out.append("page 1 shows another DOI: " + sorted(dois)[0])
    if d.page_count == 1 and p.get("kind") == "article" and len(norm(text)) < 2500:
        out.append("single page")
    return out


def pdf_version(data, p):
    """publisher | author_manuscript | preprint, judged from the first page."""
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf
    d = pymupdf.open(stream=data, filetype="pdf")
    p1 = d[0].get_text() if d.page_count else ""
    two = p1 + (d[1].get_text() if d.page_count > 1 else "")
    if p.get("status") == "preprint" or norm(p.get("journal")) in ("biorxiv", "medrxiv", "psyarxiv", "arxiv"):
        return "preprint"
    if AM_MARK.search(p1):
        return "author_manuscript"
    if PRE_MARK.search(p1):
        return "preprint"
    if p.get("doi") and p["doi"].lower() in two.lower().replace("\u200b", "").replace(" ", ""):
        return "publisher"
    j = norm(p.get("journal"))
    if j and (j in norm(two) or (len(j.split()) > 2 and " ".join(j.split()[:3]) in norm(two))):
        return "publisher"
    return "unknown"


# ---------------------------------------------------------------- DOI discovery
def find_doi(p):
    first = ((p.get("authors") or [""])[0].split(",")[0]).strip()
    q = {"query.bibliographic": p["title"], "rows": 5, "select": "DOI,title,author,type,issued"}
    if first:
        q["query.author"] = first
    d = get_json("https://api.crossref.org/works", params=q)
    for it in ((d or {}).get("message") or {}).get("items", []):
        t = (it.get("title") or [""])[0]
        if it.get("type") in ("peer-review", "component", "posted-content") and p.get("status") != "preprint":
            continue
        if difflib.SequenceMatcher(None, norm(t), norm(p["title"])).ratio() < 0.92:
            continue
        fam = [norm(a.get("family", "")) for a in it.get("author", [])]
        if first and norm(first) not in fam:
            continue
        return it["DOI"].lower()
    return None


# ---------------------------------------------------------------- candidate sources
def openalex_candidates(doi):
    key = os.environ.get("OPENALEX_API_KEY")
    w = get_json(f"https://api.openalex.org/works/doi:{doi}", params={"select": "locations,best_oa_location,ids", **({"api_key": key} if key else {})})
    out = []
    for l in (w or {}).get("locations") or []:
        if l.get("pdf_url"):
            out.append((l["pdf_url"], "publisher" if l.get("version") == "publishedVersion" else ("author_manuscript" if l.get("version") == "acceptedVersion" else "preprint"), "openalex"))
    pmcid = ((w or {}).get("ids") or {}).get("pmcid")
    return out, (pmcid.rsplit("/", 1)[-1] if pmcid else None)


def unpaywall_candidates(doi):
    email = os.environ.get("CANLAB_CONTACT_EMAIL") or getattr(config, "CONTACT_EMAIL", None)
    if not email:
        return []
    d = get_json(f"https://api.unpaywall.org/v2/{doi}", params={"email": email})
    out = []
    for l in (d or {}).get("oa_locations") or []:
        if l.get("url_for_pdf"):
            v = {"publishedVersion": "publisher", "acceptedVersion": "author_manuscript"}.get(l.get("version"), "preprint")
            out.append((l["url_for_pdf"], v, "unpaywall"))
    return out


def pmc_candidates(doi, pmcid=None, pmid=None):
    """PubMed Central copy via NCBI's PMC Open Data bucket on AWS (the sanctioned route for automated access;
    the PMC website itself puts PDFs behind a bot challenge). Only the open-access subset has PDFs there."""
    if not pmcid:
        q = f"DOI:{doi}" if doi else (f"EXT_ID:{pmid}" if pmid else None)
        d = get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search", params={"query": q, "format": "json", "resultType": "lite"}) if q else None
        for r in ((d or {}).get("resultList") or {}).get("result", []):
            if r.get("pmcid"):
                pmcid = r["pmcid"]
                break
    if not pmcid:
        return []
    bucket = "https://pmc-oa-opendata.s3.amazonaws.com/"
    try:
        listing = requests.get(bucket, params={"list-type": "2", "prefix": pmcid + "."}, headers=API_UA, timeout=30).text
    except Exception:
        return []
    keys = re.findall(r"<Key>(" + re.escape(pmcid) + r"\.(\d+)/" + re.escape(pmcid) + r"\.\d+\.json)</Key>", listing)
    if not keys:
        return []
    key = max(keys, key=lambda k: int(k[1]))[0]
    meta = get_json(bucket + key) or {}
    if not meta.get("pdf_url"):
        return []
    version = "author_manuscript" if meta.get("is_manuscript") else "publisher"
    return [(bucket + meta["pdf_url"].split("pmc-oa-opendata/", 1)[1].split("?")[0], version, "pmc-opendata")]


def publisher_candidates(sess, doi):
    """Visit the article page like a browser and collect the PDF links it advertises."""
    try:
        r = sess.get("https://doi.org/" + doi, timeout=40, allow_redirects=True)
    except Exception:
        return [], None
    page, final = r.text if r.status_code == 200 else "", r.url
    if not page or re.search(r"just a moment|cf-challenge|captcha|are you a robot", page[:5000], re.I):
        return [], final
    out = []
    for m in re.finditer(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)', page, re.I):
        out.append((htmllib.unescape(m.group(1)), "publisher", "citation_pdf_url"))
    if "journals.lww.com" in final and "/fulltext/" in final:
        out.append((final.split("?")[0].replace("/fulltext/", "/pdf/", 1), "publisher", "lww"))
    host = urllib.parse.urlparse(final).netloc
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page, re.I | re.S):
        href, label = htmllib.unescape(m.group(1)), re.sub(r"<[^>]+>", "", m.group(2)).strip().lower()
        if "supplement" in href.lower() or "sdc" in href.lower():
            continue
        if label in ("download pdf", "pdf", "view pdf", "full text pdf", "article pdf") or re.search(r"/(pdf|epdf|pdfdirect)/", href):
            u = urllib.parse.urljoin(final, href)
            if urllib.parse.urlparse(u).netloc == host:
                out.append((u, "publisher", "page-link"))
    seen, uniq = set(), []
    for c in out:
        if c[0] not in seen:
            seen.add(c[0]); uniq.append(c)
    return uniq[:6], final


def preprint_candidates(p):
    pd = p.get("preprint_doi")
    if not pd:
        return []
    c, _ = openalex_candidates(pd)
    return [(u, "preprint", "preprint-" + src) for u, _, src in c]


def download(sess, url, referer=None):
    try:
        r = sess.get(url, timeout=90, allow_redirects=True, headers={"Accept": "application/pdf,*/*;q=0.8", **({"Referer": referer} if referer else {})}, stream=True)
        if r.status_code != 200:
            return None
        data = b""
        for chunk in r.iter_content(1 << 16):
            data += chunk
            if len(data) > MAX_BYTES:
                return None
        return data if data[:5] == b"%PDF-" else None
    except Exception:
        return None


# ---------------------------------------------------------------- main
def add_pdf_link(p, path, version, source_url):
    rel = path.relative_to(ROOT / "site").as_posix()
    label = {"author_manuscript": "PDF (author manuscript)", "preprint": "PDF (preprint)"}.get(version, "PDF")
    link = {"type": "pdf", "label": label, "url": rel, "version": version}
    if source_url:
        link["url_original"] = source_url
    p["links"] = [link] + [l for l in p.get("links", []) if l.get("type") != "pdf"]
    p["has_pdf"] = True


def process(p, sess, dry=False, want_published=False):
    """want_published: only accept the publisher's version (used to upgrade a manuscript already on the site)."""
    tried = []
    # 0. a file saved by hand
    for path, version in () if want_published else ((PDF_DIR / f"{p['id']}.pdf", "publisher"), (AM_DIR / f"{p['id']}.pdf", "author_manuscript")):
        if path.exists():
            if not dry:
                add_pdf_link(p, path, version, None)
            return "linked-local", tried
    # 1. DOI and publisher link
    if not p.get("doi"):
        d = find_doi(p)
        tried.append("crossref-doi:" + (d or "none"))
        if d:
            p["doi"] = d
            p.setdefault("landing_url", "https://doi.org/" + d)
    doi = p.get("doi")
    cands = []
    if doi:
        oa, pmcid = openalex_candidates(doi)
        cands += oa + unpaywall_candidates(doi) + pmc_candidates(doi, p.get("pmcid") or pmcid, p.get("pmid"))
    elif p.get("pmid") or p.get("pmcid"):
        cands += pmc_candidates(None, p.get("pmcid"), p.get("pmid"))
    referer = None
    if doi:
        pub, referer = publisher_candidates(sess, doi)
        cands += pub
    if not want_published:
        cands += preprint_candidates(p)
    # published versions first, then author manuscripts, then preprints
    rank = {"publisher": 0, "pmc": 1, "author_manuscript": 1, "preprint": 2}
    cands.sort(key=lambda c: rank.get(c[1], 3))
    for url, version, src in cands:
        tried.append(src)
        data = download(sess, url, referer)
        if not data:
            continue
        problems = verify(data, p)
        if problems:
            tried[-1] += ":rejected(" + problems[0] + ")"
            continue
        seen = pdf_version(data, p)
        if want_published and seen != "publisher":
            tried[-1] += ":not-published-version"
            continue
        version = seen if seen != "unknown" else ("author_manuscript" if version in ("pmc", "author_manuscript") else version)
        path = (AM_DIR if version == "author_manuscript" else PDF_DIR) / f"{p['id']}.pdf"
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            add_pdf_link(p, path, version, url)
        return f"found:{src}:{version}", tried
    return "not-found", tried


def write_report(papers):
    missing = [p for p in papers if not has_pdf(p)]
    missing.sort(key=lambda p: (-(p.get("year") or 0), p["id"]))
    lines = ["# Lab papers without a PDF on the site", "",
             f"Updated {dt.date.today().isoformat()} by `pipeline/fetch_pdfs.py` (runs daily). {len(missing)} papers.", "",
             "No open-access copy could be found for these. To add one: download the PDF from the publisher link "
             "(institutional access, e.g. on the Dartmouth VPN), save it as `site/pdf/<file name>` in the repository "
             "and push; the next daily run links it on the site. Author manuscripts go in `site/pdf/author_manuscripts/`.", "",
             "| Year | Paper | Publisher link | Save as |", "|---|---|---|---|"]
    for p in missing:
        url = ("https://doi.org/" + p["doi"]) if p.get("doi") else (p.get("landing_url") or "")
        t = p["title"].replace("|", "/")
        lines.append(f"| {p.get('year') or ''} | {t[:110]} | {url or 'no DOI found'} | `{p['id']}.pdf` |")
    # published papers whose PDF on the site is a manuscript or preprint: replace with the publisher's version when you can
    pre = lambda p: p.get("status") == "preprint" or norm(p.get("journal")) in ("biorxiv", "medrxiv", "psyarxiv", "arxiv")
    ms = [(p, l) for p in papers for l in p.get("links", []) if l.get("type") == "pdf" and l.get("version") in ("author_manuscript", "preprint") and not pre(p)]
    ms.sort(key=lambda x: (-(x[0].get("year") or 0), x[0]["id"]))
    lines += ["", "## Published papers whose PDF is a manuscript or preprint", "",
              f"{len(ms)} papers. The site labels these \"PDF (author manuscript)\" or \"PDF (preprint)\". The daily run looks for an "
              "open-access published version once a month; to replace one by hand, save the publisher's PDF over the file named here and push.", "",
              "| Year | Paper | Now | Publisher link | File |", "|---|---|---|---|---|"]
    for p, l in ms:
        url = ("https://doi.org/" + p["doi"]) if p.get("doi") else (p.get("landing_url") or "")
        lines.append(f"| {p.get('year') or ''} | {p['title'].replace('|', '/')[:100]} | {l['version'].replace('_', ' ')} | {url or 'no DOI'} | `site/{l['url']}` |")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n")
    return len(missing)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="comma-separated paper ids (default: every paper without a PDF that is due)")
    ap.add_argument("--force", action="store_true", help="ignore the retry schedule")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=40, help="at most this many papers per run")
    a = ap.parse_args(argv)
    today = dt.date.today()
    papers = json.loads(PAPERS.read_text())
    ids = set(a.ids.split(",")) if a.ids else None
    local = lambda p: (PDF_DIR / f"{p['id']}.pdf").exists() or (AM_DIR / f"{p['id']}.pdf").exists()
    todo = [p for p in papers if not has_pdf(p) and (p["id"] in ids if ids else (local(p) or due(p, today, a.force)))][: a.max]
    print(f"{sum(1 for p in papers if not has_pdf(p))} papers without a PDF; checking {len(todo)}")
    sess = requests.Session()
    sess.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})
    found = 0
    for p in todo:
        result, tried = process(p, sess, a.dry_run)
        found += result != "not-found"
        p["pdf_search"] = {"last": today.isoformat(), "result": result, "tried": tried[:12]}
        print(f"  {p['id']}: {result}  ({', '.join(tried[:8])})", flush=True)
        time.sleep(1)
    # monthly: papers whose PDF is an author manuscript or preprint, though the paper is published, are re-checked
    # for the publisher's open-access version, which replaces the manuscript when found
    def upgradable(p):
        l = next((l for l in p.get("links", []) if l.get("type") == "pdf"), None)
        if not l or l.get("version") in (None, "publisher") or not p.get("doi") or p.get("status") == "preprint":
            return False
        if norm(p.get("journal")) in ("biorxiv", "medrxiv", "psyarxiv", "arxiv"):
            return False
        last = (p.get("pdf_upgrade") or {}).get("last")
        return a.force or not last or (today - dt.date.fromisoformat(last)).days >= 30
    up = [p for p in papers if not ids and upgradable(p)][: max(0, a.max - len(todo))]
    for p in up:
        l = next(l for l in p["links"] if l["type"] == "pdf")
        old = ROOT / "site" / l["url"]
        result, tried = process(p, sess, a.dry_run, want_published=True)
        if result.startswith("found") and not a.dry_run:
            new = ROOT / "site" / next(x for x in p["links"] if x["type"] == "pdf")["url"]
            if old.exists() and old.resolve() != new.resolve():
                old.unlink()
            found += 1
        p["pdf_upgrade"] = {"last": today.isoformat(), "result": result, "tried": tried[:12]}
        print(f"  upgrade {p['id']}: {result}", flush=True)
        time.sleep(1)
    if not a.dry_run:
        PAPERS.write_text(json.dumps(papers, indent=1, ensure_ascii=False))
        n = write_report(papers)
        print(f"attached {found}; {n} still without a PDF -> {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
