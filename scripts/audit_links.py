"""Audit the publisher links of every paper in data/papers.json (the site's "Publisher" button is the explicit
publisher link when there is one, otherwise https://doi.org/<doi>).

  1. every DOI is registered (doi.org handle API) and its Crossref record is this paper (title similarity,
     first-author surname, year within 2), and is not a component/peer review/meeting abstract of it;
  2. every explicit publisher/preprint link answers (HTTP), and when the page is readable its citation_title /
     og:title / <title> matches the paper; pages that answer with a bot check are reported as "blocked", not broken;
  3. papers with neither a DOI nor a publisher link are searched in Crossref (pipeline.fetch_pdfs.find_doi).
Writes work/link_audit.json. Usage: python scripts/audit_links.py
"""
import difflib
import html as htmllib
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.fetch_pdfs import BROWSER_UA, find_doi, norm  # noqa: E402

API = {"User-Agent": "canlab-site/1.0 (https://canlab.science; link audit)"}


def sim(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0
    if a in b or b in a:
        return 1.0 if min(len(a), len(b)) > 25 else 0.9
    return difflib.SequenceMatcher(None, a, b).ratio()


def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, timeout=40, **kw)
            if r.status_code in (429, 503):
                time.sleep(5 * (i + 1)); continue
            return r
        except Exception:
            time.sleep(3)
    return None


def check_doi(p):
    doi = p["doi"]
    h = get("https://doi.org/api/handles/" + doi, headers=API)
    if not h or h.status_code != 200 or h.json().get("responseCode") != 1:
        return ["DOI not registered at doi.org"]
    r = get("https://api.crossref.org/works/" + requests.utils.quote(doi), headers=API)
    if not r or r.status_code != 200:
        return []  # DataCite DOIs (Zenodo, OSF) are not in Crossref; registered is enough
    m = r.json()["message"]
    out = []
    t = (m.get("title") or [""])[0]
    s = sim(t, p["title"])
    if s < 0.85:
        out.append(f"DOI title differs ({s:.2f}): {t[:90]!r}")
    if m.get("type") in ("component", "peer-review", "reference-entry") or re.search(r"\(\d+\)\s", t[:8]):
        out.append(f"DOI is a {m.get('type')}")
    fam = [norm(a.get("family", "")) for a in m.get("author", [])]
    first = norm((p.get("authors") or [""])[0].split(",")[0])
    if fam and first and first not in fam and not any(first in f or f in first for f in fam):
        out.append(f"first author {first!r} not among DOI authors {fam[:4]}")
    y = ((m.get("issued") or {}).get("date-parts") or [[None]])[0][0]
    if y and p.get("year") and abs(int(y) - int(p["year"])) > 2:
        out.append(f"year {p['year']} vs DOI {y}")
    return out


def page_title(html):
    for pat in (r'<meta[^>]+name=["\']citation_title["\'][^>]+content=["\']([^"\']+)', r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)', r"<title[^>]*>(.*?)</title>"):
        m = re.search(pat, html, re.I | re.S)
        if m:
            return htmllib.unescape(m.group(1)).strip()
    return ""


def check_url(p, url, sess):
    r = get(url, headers={"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"}, allow_redirects=True)
    if r is None:
        return "error", ["no response"]
    blocked = r.status_code in (401, 403, 429, 503) or re.search(r"just a moment|cf-challenge|captcha|are you a robot|access denied|POW_CHALLENGE", r.text[:6000], re.I)
    if blocked:
        return "blocked", [f"HTTP {r.status_code}: site refuses automated checks"]
    if r.status_code >= 400:
        return "broken", [f"HTTP {r.status_code} at {r.url}"]
    t = page_title(r.text)
    if "pdf" in r.headers.get("content-type", ""):
        return "ok", []
    if t and sim(t, p["title"]) < 0.6 and not re.search(r"pubmed|biorxiv|psyarxiv|osf", r.url):
        return "mismatch", [f"page title {t[:90]!r}"]
    return "ok", []


def main():
    papers = json.loads((ROOT / "data" / "papers.json").read_text())
    out = {"doi": {}, "links": {}, "no_link": {}}
    for n, p in enumerate(papers, 1):
        if p.get("doi"):
            issues = check_doi(p)
            if issues:
                out["doi"][p["id"]] = {"doi": p["doi"], "issues": issues}
                print(f"DOI   {p['id']}: {p['doi']} :: {'; '.join(issues)}", flush=True)
            time.sleep(0.25)
        for l in p.get("links", []):
            if l["type"] in ("publisher", "preprint"):
                status, why = check_url(p, l["url"], None)
                if status != "ok":
                    out["links"][p["id"] + " " + l["url"]] = {"status": status, "why": why}
                    print(f"LINK  {p['id']}: {status} {l['url']} :: {'; '.join(why)}", flush=True)
                time.sleep(0.5)
        if not p.get("doi") and not any(l["type"] in ("publisher", "preprint") for l in p.get("links", [])):
            d = find_doi(p)
            out["no_link"][p["id"]] = d
            print(f"NONE  {p['id']}: found DOI {d}" if d else f"NONE  {p['id']}: no DOI found", flush=True)
            time.sleep(0.5)
        if n % 100 == 0:
            print(f"... {n}/{len(papers)}", file=sys.stderr, flush=True)
    (ROOT / "work").mkdir(exist_ok=True)
    (ROOT / "work" / "link_audit.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print({k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
