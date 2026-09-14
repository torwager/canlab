"""Curate journal-club items: decide what is a paper, decode redirect/safelink URLs, and repair titles that were
captured from bot-block pages ("Just a moment...") by resolving the DOI from the URL (bioRxiv/medRxiv/arXiv/
Nature/Cell/ScienceDirect patterns) or Crossref. Runs at the end of slack_articles and standalone:
python -m pipeline.jc_curate
"""
import json, re, sys, time, urllib.parse
import requests
from . import config

OUT = config.DATA / "journal_club.json"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
PAPER_HOSTS = ("nature.com", "sciencedirect.com", "biorxiv.org", "medrxiv.org", "ncbi.nlm.nih.gov", "cell.com", "science.org", "sciencemag.org", "doi.org", "pnas.org", "arxiv.org",
               "journals.lww.com", "plos.org", "wiley.com", "psyarxiv.com", "osf.io", "jamanetwork.com", "springer.com", "oup.com", "frontiersin.org", "jneurosci.org", "psycnet.apa.org",
               "elifesciences.org", "sagepub.com", "nejm.org", "mit.edu", "rdcu.be", "researchgate.net", "tandfonline.com", "cambridge.org", "karger.com", "bmj.com", "thelancet.com",
               "annualreviews.org", "mdpi.com", "hindawi.com", "biomedcentral.com", "springeropen.com", "iop.org", "ieee.org", "acm.org", "ssrn.com", "europepmc.org", "semanticscholar.org",
               "paperpile.com", "psychiatryonline.org", "physiology.org", "royalsocietypublishing.org", "jstor.org", "neurology.org", "aacrjournals.org", "ahajournals.org", "jci.org", "embopress.org", "rupress.org", "cshlp.org")
BAD_TITLES = re.compile(r"^(just a moment|access denied|redirecting|are you a robot|attention required|error|403|404|page not found|loading|sciencedirect|nature|science|pubmed|home)\b|cloudflare|captcha|verify you are", re.I)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>|)\]}#?]+", re.I)


def host(u):
    return urllib.parse.urlparse(u).netloc.lower().replace("www.", "")


def decode_redirect(u):
    p = urllib.parse.urlparse(u)
    if "safelinks.protection.outlook.com" in p.netloc or (p.netloc.endswith("scholar.google.com") and "scholar_url" in p.path):
        q = urllib.parse.parse_qs(p.query).get("url")
        if q:
            return decode_redirect(q[0])
    if p.netloc.endswith("rdcu.be") or p.netloc in ("t.co", "bit.ly", "tinyurl.com", "goo.gl"):
        try:
            return requests.head(u, headers=UA, allow_redirects=True, timeout=20).url
        except Exception:
            pass
    return u


def clean_doi(d):
    d = d.rstrip(".,;)").lower()
    d = re.sub(r"(\.full(\.pdf)?|\.abstract|\.pdf|\.short)$", "", d)
    d = re.sub(r"v\d+$", "", d) if d.startswith(("10.1101/", "10.64898/", "10.48550/")) else d
    return d


def doi_from_url(u):
    p = urllib.parse.urlparse(u); path = urllib.parse.unquote(p.path); h = host(u)
    m = DOI_RE.search(path)
    if m:
        return clean_doi(m.group(0))
    if h == "academic.oup.com":
        m = re.search(r"^/([a-z]+)/(?:article|article-abstract|advance-article)/(?:\d+/\d+/)?([A-Za-z0-9]+)/\d+", path)
        if m: return f"10.1093/{m.group(1)}/{m.group(2)}"
    if h == "nature.com":
        m = re.search(r"/articles/([A-Za-z0-9.\-]+)", path)
        if m: return "10.1038/" + m.group(1).lower()
    if h in ("biorxiv.org", "medrxiv.org"):
        m = re.search(r"/early/\d{4}/\d{2}/\d{2}/(\d{4}\.\d{2}\.\d{2}\.\d+)", path)
        if m: return ("10.64898/" if m.group(1) >= "2026" else "10.1101/") + m.group(1)
    if h == "arxiv.org":
        m = re.search(r"/(?:abs|pdf)/(\d{4}\.\d{4,5})", path)
        if m: return "10.48550/arxiv." + m.group(1)
    pii = None
    if h == "cell.com":
        m = re.search(r"/(?:fulltext|abstract|pdf)/(S\d{4}-\d{4}\(\d{2}\)\d{5}-[\dX])", path)
        if m: pii = re.sub(r"[^0-9SX]", "", m.group(1))
    if h in ("sciencedirect.com", "linkinghub.elsevier.com"):
        m = re.search(r"/pii/(S\d{15}[\dX])", path) or re.search(r"/(S\d{15}[\dX])", path)
        if m: pii = m.group(1)
    if pii:
        try:
            j = requests.get("https://api.crossref.org/works", params={"filter": "alternative-id:" + pii, "rows": 1}, headers={"User-Agent": "canlab-site journal club/1.0"}, timeout=30).json()
            items = j["message"]["items"]
            if items: return items[0]["DOI"].lower()
        except Exception:
            pass
    return None


def crossref_meta(doi):
    try:
        r = requests.get("https://api.crossref.org/works/" + urllib.parse.quote(doi), headers={"User-Agent": "canlab-site journal club/1.0"}, timeout=30)
        if r.status_code != 200: return None
        w = r.json()["message"]
        dp = (w.get("issued") or w.get("created") or {}).get("date-parts", [[None]])[0]
        return {"title": (w.get("title") or [""])[0], "journal": (w.get("container-title") or [""])[0], "year": dp[0] if dp else None,
                "authors": [f"{a.get('family','')}, {' '.join(x[0] + '.' for x in a.get('given','').split())}".strip(", ") for a in w.get("author", []) if a.get("family")],
                "abstract": re.sub(r"<[^>]+>", " ", w.get("abstract") or "").strip() or None}
    except Exception:
        return None


def arxiv_meta(aid):
    """arXiv metadata from the abstract page's citation_* meta tags (the export API is not reachable from everywhere)."""
    try:
        h = requests.get(f"https://arxiv.org/abs/{aid}", headers=UA, timeout=30).text
        g = lambda name: re.findall(r'<meta name="%s" content="([^"]*)"' % name, h)
        t = g("citation_title"); au = g("citation_author"); d = g("citation_date")
        ab = re.search(r'<blockquote class="abstract[^"]*">\s*(?:<span[^>]*>Abstract:</span>)?(.*?)</blockquote>', h, re.S)
        if not t: return None
        import html as _h
        return {"title": _h.unescape(t[0]).strip(), "authors": [_h.unescape(a) for a in au], "journal": "arXiv", "year": int(d[0][:4]) if d else None,
                "abstract": re.sub(r"\s+", " ", _h.unescape(re.sub(r"<[^>]+>", " ", ab.group(1)))).strip() if ab else None}
    except Exception:
        return None


def biorxiv_meta(doi):
    for srv in ("biorxiv", "medrxiv"):
        try:
            j = requests.get(f"https://api.biorxiv.org/details/{srv}/{doi}", headers=UA, timeout=30).json()
            if not j.get("collection") and doi.startswith("10.1101/") and doi[8:12] >= "2026":
                j = requests.get(f"https://api.biorxiv.org/details/{srv}/10.64898/{doi[8:]}", headers=UA, timeout=30).json()
            c = (j.get("collection") or [None])[-1]
            if c: return {"title": c["title"], "abstract": c.get("abstract"), "authors": [a.strip() for a in c.get("authors", "").split(";") if a.strip()], "journal": srv.replace("rxiv", "Rxiv"), "year": int(c["date"][:4])}
        except Exception:
            pass
    return None


def is_paper(it):
    if it.get("doi") or it.get("pmid") or it.get("pmcid"): return True
    return any(host(it["url"]).endswith(h) for h in PAPER_HOSTS)


def curate(items):
    n_fixed = n_paper = 0
    for i, it in enumerate(items):
        u2 = decode_redirect(it["url"])
        if u2 != it["url"]:
            it["url_original"], it["url"] = it["url"], u2
        bad = not it.get("title") or it["title"] in (it.get("url"), it.get("url_original")) or bool(BAD_TITLES.match(it["title"].strip()))
        if bad or not it.get("doi"):
            doi = it.get("doi") or doi_from_url(it["url"])
            meta = None
            if doi and doi.startswith("10.48550/arxiv."):
                meta = arxiv_meta(doi.split("arxiv.")[1])
            elif doi and doi.startswith(("10.1101/", "10.64898/")):
                meta = biorxiv_meta(doi) or crossref_meta(doi)
            elif doi:
                meta = crossref_meta(doi)
            if meta and meta.get("title"):
                it["doi"] = doi
                it.setdefault("publisher_url", "https://doi.org/" + doi)
                for k, v in meta.items():
                    if v and (bad or not it.get(k)): it[k] = v
                if bad: n_fixed += 1
            if doi: time.sleep(0.3)
        it["kind"] = "paper" if is_paper(it) else "link"
        n_paper += it["kind"] == "paper"
        if BAD_TITLES.match((it.get("title") or "").strip()) or it["title"] in (it.get("url"), it.get("url_original")):
            it["title_unresolved"] = True
            msg = re.sub(r"https?://\S+", "", it.get("message") or "").strip().split("\n")[0].strip(" *_\"“”")
            if 12 < len(msg) < 160:
                it["title"] = msg
        else:
            it.pop("title_unresolved", None)
        if i and i % 100 == 0: print(f"  {i}/{len(items)} curated", file=sys.stderr, flush=True)
    return n_fixed, n_paper


def main():
    store = json.load(open(OUT))
    n_fixed, n_paper = curate(store["items"])
    json.dump(store, open(OUT, "w"), indent=1, ensure_ascii=False)
    unresolved = sum(1 for it in store["items"] if it.get("title_unresolved"))
    print(f"{len(store['items'])} items: {n_paper} papers, {len(store['items']) - n_paper} other links; {n_fixed} titles repaired; {unresolved} still unresolved")


if __name__ == "__main__":
    main()
