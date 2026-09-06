"""OpenAlex: author works search (daily discovery), enrichment by DOI/PMID/title, citation refresh."""
import time
import requests
from . import config

OA = "https://api.openalex.org/works"
H = {"User-Agent": config.TOOL_NAME}
SELECT = "id,doi,title,authorships,publication_date,publication_year,type,primary_location,open_access,best_oa_location,ids,abstract_inverted_index,keywords,cited_by_count,biblio,language"


def _p(extra):
    p = {}
    if config.CONTACT_EMAIL:
        p["mailto"] = config.CONTACT_EMAIL
    if config.OPENALEX_API_KEY:
        p["api_key"] = config.OPENALEX_API_KEY
    p.update(extra)
    return p


def _get(url, params, retries=5):
    for i in range(retries):
        r = requests.get(url, headers=H, params=_p(params), timeout=60)
        if r.status_code == 429:
            time.sleep(15 * (i + 1)); continue
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    raise RuntimeError("OpenAlex rate limit")


def _abstract(inv):
    if not inv:
        return ""
    pos = {}
    for w, idxs in inv.items():
        for i in idxs:
            pos[i] = w
    return " ".join(pos[i] for i in sorted(pos))


def author_works(author_id, from_date, per_page=100):
    """All works by an OpenAlex author id published since from_date (YYYY-MM-DD)."""
    out, cursor = [], "*"
    while cursor:
        j = _get(OA, {"filter": f"authorships.author.id:{author_id},from_publication_date:{from_date}", "per-page": per_page, "cursor": cursor, "select": SELECT, "sort": "publication_date:desc"})
        if not j:
            break
        out.extend(j.get("results", []))
        cursor = (j.get("meta") or {}).get("next_cursor") if j.get("results") else None
        time.sleep(1.0)
    return out


def by_doi(doi):
    return _get(f"{OA}/https://doi.org/{doi}", {"select": SELECT}) if doi else None


def by_pmid(pmid):
    return _get(f"{OA}/pmid:{pmid}", {"select": SELECT}) if pmid else None


def to_record(w):
    ids = w.get("ids") or {}
    src = (w.get("primary_location") or {}).get("source") or {}
    b = w.get("biblio") or {}
    auth = []
    for a in w.get("authorships") or []:
        n = (a.get("author") or {}).get("display_name") or ""
        parts = n.split()
        if len(parts) >= 2:
            auth.append(f"{parts[-1]}, {' '.join(p[0] + '.' for p in parts[:-1])}")
        elif n:
            auth.append(n)
    return {
        "title": w.get("title") or "", "authors": auth,
        "authors_short": [a.split(",")[0] + " " + "".join(ch for ch in a.split(",")[1] if ch.isupper()) if "," in a else a for a in auth],
        "year": w.get("publication_year"), "date": w.get("publication_date") or "",
        "status": "preprint" if w.get("type") == "preprint" else "published", "kind": "preprint" if w.get("type") == "preprint" else ("chapter" if w.get("type") == "book-chapter" else "article"),
        "journal": src.get("display_name") or ("Preprint" if w.get("type") == "preprint" else ""),
        "volume": b.get("volume"), "issue": b.get("issue"), "pages": (f"{b['first_page']}-{b['last_page']}" if b.get("first_page") and b.get("last_page") else b.get("first_page")),
        "doi": (w.get("doi") or "").replace("https://doi.org/", "").lower() or None,
        "pmid": (ids.get("pmid") or "").rsplit("/", 1)[-1] or None, "pmcid": (ids.get("pmcid") or "").rsplit("/", 1)[-1] or None,
        "openalex_id": w.get("id"), "abstract": _abstract(w.get("abstract_inverted_index")),
        "cited_by_count": w.get("cited_by_count"), "oa_status": (w.get("open_access") or {}).get("oa_status"),
        "oa_url": (w.get("best_oa_location") or {}).get("pdf_url") or (w.get("open_access") or {}).get("oa_url"),
        "landing_url": (w.get("primary_location") or {}).get("landing_page_url"),
        "keywords": [k.get("display_name") for k in (w.get("keywords") or []) if k.get("display_name")][:10],
        "links": [], "source": "openalex",
    }


def refresh_citations(papers, max_n=None):
    """Update cited_by_count (and missing abstracts/ids) for papers with a DOI or PMID. Returns the number updated."""
    n = 0
    for r in papers:
        if max_n and n >= max_n:
            break
        if not (r.get("doi") or r.get("pmid")):
            continue
        try:
            w = by_doi(r.get("doi")) or by_pmid(r.get("pmid"))
        except Exception:  # noqa: BLE001
            continue
        if not w:
            continue
        r["cited_by_count"] = w.get("cited_by_count", r.get("cited_by_count"))
        if not r.get("abstract"):
            r["abstract"] = _abstract(w.get("abstract_inverted_index"))
        if not r.get("pmid") and (w.get("ids") or {}).get("pmid"):
            r["pmid"] = w["ids"]["pmid"].rsplit("/", 1)[-1]
        if not r.get("oa_url"):
            r["oa_url"] = (w.get("best_oa_location") or {}).get("pdf_url")
        n += 1
        time.sleep(1.0)
    return n
