"""Apply the publisher-link audit of 2026-10-09 (scripts/audit_links.py, reviewed by hand). Idempotent.

- DOIs that pointed at an eLife peer-review report instead of the article
- titles that changed at publication (taken from the DOI's Crossref record)
- DOIs found for papers that had no publisher link at all (each checked: title, authors, book)
- tracking parameters stripped from explicit publisher links
- every preprint_doi becomes a visible "Preprint" link (the site showed no link for preprint-only papers)
"""
import json
import sys
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import refs  # noqa: E402

H = {"User-Agent": "canlab-site/1.0 (https://canlab.science; link fixes)"}
NEW_DOI = {
    "englert2026functional": "10.7554/elife.98725",            # was ...98725.3.sa2 (peer review)
    "zhouf2020empathic": "10.7554/elife.56929",                 # was ...56929.sa1 (peer review)
    "lee2026functional": "10.1162/netn.a.609",                  # published under a new title
    "wager2007elements": "10.1017/cbo9780511546396.002",
    "botviniknezerr2023advancing": "10.4135/9781529616613.n34",
    "lindquist2008application": "10.4324/9780203843147-11",
    "atlas2009placebo": "10.1016/b978-012373873-8.00029-3",     # the Encyclopedia of Consciousness entry the PDF is
}
TITLE_FROM_CROSSREF = {"kragel2020fmri", "lopezsola2018transforming", "lopezsola2014altered", "lee2026functional", "atlas2009placebo"}
EXTRA_LINKS = {  # the lab's reply shares a DOI with the letter it answers, so link it rather than claim the DOI
    "wager2004painful": {"type": "publisher", "label": "Publisher (letter and response)", "url": "https://doi.org/10.1126/science.304.5674.1109c"},
}
TRACKING = ("utm_", "dgcid", "via", "SIS_ID", "CMX_ID", "redirectedFrom", "rss", "ref")


def crossref(doi):
    for i in range(5):
        r = requests.get("https://api.crossref.org/works/" + urllib.parse.quote(doi), headers=H, timeout=40)
        if r.status_code == 200:
            return r.json()["message"]
        time.sleep(4 * (i + 1))
    raise RuntimeError(doi)


def registered(doi):
    try:
        return requests.get("https://doi.org/api/handles/" + doi, headers=H, timeout=30).json().get("responseCode") == 1
    except Exception:
        return False


def clean(url):
    u = urllib.parse.urlsplit(url)
    q = [(k, v) for k, v in urllib.parse.parse_qsl(u.query, keep_blank_values=True) if not k.startswith(TRACKING)]
    return urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, urllib.parse.urlencode(q), u.fragment))


def main():
    path = ROOT / "data" / "papers.json"
    papers = json.loads(path.read_text())
    by = {p["id"]: p for p in papers}
    log = []
    for pid, doi in NEW_DOI.items():
        p = by[pid]
        if p.get("doi") != doi:
            log.append(f"{pid}: doi {p.get('doi')} -> {doi}")
            p["doi"], p["landing_url"], p["cited_by_count"] = doi, "https://doi.org/" + doi, None
            p.pop("openalex_id", None)
    for pid in TITLE_FROM_CROSSREF:
        p = by[pid]
        m = crossref(p["doi"])
        t = " ".join((m.get("title") or [""])[0].split())
        if (m.get("subtitle") or [None])[0] and ":" not in t:
            t += ": " + " ".join(m["subtitle"][0].split())
        if t and p["title"] != t:
            log.append(f"{pid}: title {p['title']!r} -> {t!r}")
            p["title"] = t
        time.sleep(1)
    for pid, link in EXTRA_LINKS.items():
        p = by[pid]
        if not any(l.get("url") == link["url"] for l in p.get("links", [])):
            p.setdefault("links", []).append(link)
            log.append(f"{pid}: added {link['label']}")
    for p in papers:
        for l in p.get("links", []):
            if l["type"] in ("publisher", "preprint") and "?" in l["url"]:
                c = clean(l["url"])
                if c != l["url"]:
                    log.append(f"{p['id']}: cleaned {l['url'][:70]}")
                    l["url"] = c
        pd = (p.get("preprint_doi") or "").lower()
        if pd and pd != (p.get("doi") or "").lower() and not any(l["type"] == "preprint" for l in p.get("links", [])):
            if registered(pd):
                p.setdefault("links", []).append({"type": "preprint", "label": "Preprint", "url": "https://doi.org/" + pd})
                log.append(f"{p['id']}: preprint link {pd}")
            else:
                log.append(f"{p['id']}: preprint_doi {pd} NOT registered; left out")
            time.sleep(0.3)
    for pid in set(NEW_DOI) | TITLE_FROM_CROSSREF | set(EXTRA_LINKS):
        by[pid]["citation"] = refs.make_citation(by[pid])
    path.write_text(json.dumps(papers, indent=1, ensure_ascii=False))
    print("\n".join(log))


if __name__ == "__main__":
    main()
