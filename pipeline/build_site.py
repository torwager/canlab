"""Build the static site's data files and pre-rendered paper pages from data/ into site/.

Outputs:
  site/data/index.json         slim record per paper (drives publications, filters, network, lists)
  site/data/papers.json        full records keyed by id (abstract, links, classification)
  site/data/text.json          id + title + abstract + keywords for client-side full-text search
  site/data/taxonomy.json      chip labels/colours
  site/data/stats.json         counts, last-updated
  site/data/bibliometrics.json aggregates for the bibliometrics page
  site/data/{people,news_posts,news,research,resources,join,candidates}.json  copied from data/
  site/papers/<id>.html        pre-rendered paper pages (SEO, social previews, JSON-LD) that load the same JS
  site/feed.xml, sitemap.xml, robots.txt
"""
import html
import re
import json
import shutil
import time
from collections import Counter, defaultdict
from xml.sax.saxutils import escape
from . import config

SITE_URL = config.SITE_URL


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def short_authors(auth):
    if not auth:
        return ""
    sur = lambda a: a.split(",")[0].strip()
    if len(auth) == 1:
        return sur(auth[0])
    if len(auth) == 2:
        return f"{sur(auth[0])} & {sur(auth[1])}"
    return f"{sur(auth[0])} et al."


def author_line(auth):
    if len(auth) <= 2:
        return " & ".join(auth)
    return ", ".join(auth[:-1]) + ", & " + auth[-1]


def publisher_url(r):
    for l in r.get("links", []):
        if l["type"] in ("publisher", "preprint") and "sites.dartmouth.edu" not in l["url"]:
            return l["url"]
    if r.get("doi"):
        return "https://doi.org/" + r["doi"]
    return r.get("landing_url") or ""


def pdf_link(r):
    for l in r.get("links", []):
        if l["type"] == "pdf":
            return l
    return None


# Author strings ("Surname II") come from citations typed by hand over 25 years; merge known variants of the same person.
AUTHOR_ALIASES = {"Feldman Barrett L": "Barrett LF", "Feldmann-Barrett L": "Barrett LF", "Feldmann Barrett L": "Barrett LF", "Feldman-Barrett L": "Barrett LF", "Barrett L": "Barrett LF", "Lindquist M": "Lindquist MA", "Wager T": "Wager TD",
                  "Woo C": "Woo CW", "Woo C-W": "Woo CW", "Kragel P": "Kragel PA", "Atlas L": "Atlas LY", "Lopez-Sola M": "López-Solà M", "Lopez-Sola M": "López-Solà M", "Ceko M": "Čeko M", "Losin E": "Losin EAR", "Losin EA": "Losin EAR",
                  "Botvinik-Nezer R": "Botvinik-Nezer R", "Andrews-Hanna J": "Andrews-Hanna JR", "Gianaros P": "Gianaros PJ", "Koban L": "Koban L", "Jepma M": "Jepma M", "Ochsner K": "Ochsner KN", "Smith E": "Smith EE", "Jonides J": "Jonides J", "Kober H": "Kober H", "Chang L": "Chang LJ", "Roy M": "Roy M", "Bingel U": "Bingel U", "Zorina-Lichtenwalter K": "Zorina-Lichtenwalter K"}


def canonical_author(a):
    a = re.sub(r"Feldmann?[ -]Barrett", "Barrett", a).strip()
    if a in AUTHOR_ALIASES:
        return AUTHOR_ALIASES[a]
    return a


def merge_author_variants(papers):
    """Same surname + same first initial, one initial string a prefix of the other -> use the longer (more specific) form."""
    from collections import Counter
    counts = Counter(a for r in papers for a in (r.get("authors_short") or []))
    by_sur = {}
    for a in counts:
        parts = a.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isupper():
            by_sur.setdefault(parts[0].lower(), []).append(a)
    alias = {}
    for sur, names in by_sur.items():
        names.sort(key=lambda n: (-len(n.rsplit(" ", 1)[1]), -counts[n]))
        for short in names:
            ini = short.rsplit(" ", 1)[1]
            for long in names:
                lini = long.rsplit(" ", 1)[1]
                if long != short and lini.startswith(ini) and len(lini) > len(ini):
                    alias[short] = long
                    break
    for r in papers:
        r["authors_short"] = list(dict.fromkeys(alias.get(canonical_author(a), canonical_author(a)) for a in (r.get("authors_short") or [])))
    return alias


def slim(r):
    tags = {k: (v if isinstance(v, list) else [v]) for k, v in (r.get("tags") or {}).items() if v}
    pdf = pdf_link(r)
    return {
        "id": r["id"], "t": r["title"], "a": short_authors(r["authors"]), "al": author_line(r["authors"]), "au": r.get("authors_short") or [],
        "y": r.get("year"), "d": r.get("date") or "", "st": r.get("status"), "kind": r.get("kind"),
        "j": r.get("journal") or "", "vol": r.get("volume"), "issue": r.get("issue"), "pg": r.get("pages"),
        "doi": r.get("doi"), "pmid": r.get("pmid"), "u": publisher_url(r),
        "pdf": (pdf.get("mirror") or pdf["url"]) if pdf else None, "oa": r.get("oa_url"),
        "links": r.get("links", []), "s": r.get("summary") or "", "cit": r.get("cited_by_count"),
        "tags": tags, "kw": (r.get("free_keywords") or [])[:8], "added": r.get("date_added") or "", "ab": bool(r.get("abstract")),
        "comm": r.get("commentaries") or [], "trunc": bool(r.get("authors_truncated")),
    }


# ----------------------------------------------------------------------------- pre-rendered paper pages
PAPER_TEMPLATE = None


def paper_page(r, s, tax, related):
    global PAPER_TEMPLATE
    if PAPER_TEMPLATE is None:
        PAPER_TEMPLATE = (config.SITE / "paper.html").read_text()
    title = r["title"]
    desc = (r.get("summary") or (r.get("abstract") or "")[:200] or f"{s['al']} ({r.get('year')}). {r.get('journal', '')}").strip()
    url = f"{SITE_URL}/papers/{r['id']}.html"
    pdf = pdf_link(r)
    ld = {"@context": "https://schema.org", "@type": "ScholarlyArticle", "headline": title, "name": title, "url": url,
          "author": [{"@type": "Person", "name": a} for a in r["authors"][:60]],
          "datePublished": r.get("date") or (str(r["year"]) if r.get("year") else None), "isPartOf": {"@type": "Periodical", "name": r.get("journal") or ""},
          "abstract": (r.get("abstract") or "")[:2000] or None, "keywords": ", ".join(s["kw"]) or None,
          "identifier": [x for x in [({"@type": "PropertyValue", "propertyID": "DOI", "value": r["doi"]} if r.get("doi") else None), ({"@type": "PropertyValue", "propertyID": "PMID", "value": r["pmid"]} if r.get("pmid") else None)] if x],
          "sameAs": [x for x in [("https://doi.org/" + r["doi"]) if r.get("doi") else None, ("https://pubmed.ncbi.nlm.nih.gov/" + str(r["pmid"]) + "/") if r.get("pmid") else None] if x],
          "publisher": {"@type": "Organization", "name": "Cognitive and Affective Neuroscience Lab, Dartmouth College"}}
    if pdf:
        ld["encoding"] = {"@type": "MediaObject", "encodingFormat": "application/pdf", "contentUrl": pdf.get("mirror") or pdf["url"]}
    ld = {k: v for k, v in ld.items() if v}
    labels = {(ax["id"], v["id"]): v["label"] for ax in tax["axes"] for v in ax["values"]}
    chips = "".join(f'<a class="chip static" href="../publications.html?{ax}={v}">{esc(labels.get((ax, v), v))}</a>' for ax in ("topic", "approach", "type") for v in s["tags"].get(ax, []))
    links = []
    if pdf:
        links.append(f'<a class="btn primary" href="{esc(pdf.get("mirror") or pdf["url"])}">PDF</a>')
    if s["u"]:
        links.append(f'<a class="btn" href="{esc(s["u"])}">Publisher ↗</a>')
    for l in r.get("links", []):
        if l["type"] not in ("pdf", "publisher"):
            links.append(f'<a class="btn" href="{esc(l["url"])}">{esc(l["label"])}</a>')
    static = f"""<div class="meta small muted">{esc(r.get('journal') or '')} · {esc(r.get('year') or '')}</div>
    <h1>{esc(title)}</h1>
    <div class="small">{esc(s['al'])}</div>
    <div class="links" style="display:flex;gap:.5rem;flex-wrap:wrap">{''.join(links)}</div>
    {('<div class="callout"><b>In one sentence.</b> ' + esc(r['summary']) + '</div>') if r.get('summary') else ''}
    <div><h3 style="margin-bottom:.3rem">Abstract</h3><div class="abstract">{esc(r.get('abstract') or 'No abstract available; see the publisher page.')}</div></div>
    <div><h3 style="margin-bottom:.5rem">Keywords</h3><div class="chips">{chips}</div></div>
    <p class="small muted">Citation: {esc(r.get('citation') or '')}</p>"""
    rel = "".join(f'<li><a href="{esc(x["id"])}.html">{esc(x["t"])}</a> <span class="muted">({x["y"] or ""})</span></li>' for x in related)
    page = PAPER_TEMPLATE
    page = page.replace("{{TITLE}}", esc(title)).replace("{{DESC}}", esc(desc[:300])).replace("{{URL}}", esc(url)).replace("{{ID}}", esc(r["id"]))
    page = page.replace("{{JSONLD}}", json.dumps(ld, ensure_ascii=False)).replace("{{STATIC}}", static).replace("{{RELATED}}", rel)
    return page


def related_papers(s, index, k=6):
    mine = {(ax, v) for ax, vs in s["tags"].items() for v in vs if ax != "type"}
    if not mine:
        return []
    scored = []
    for o in index:
        if o["id"] == s["id"]:
            continue
        theirs = {(ax, v) for ax, vs in o["tags"].items() for v in vs if ax != "type"}
        inter = len(mine & theirs)
        if inter >= 2:
            scored.append((inter / (len(mine | theirs) or 1), o["cit"] or 0, o))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [o for _, _, o in scored[:k]]


# ----------------------------------------------------------------------------- aggregates
def bibliometrics(papers, index):
    by_year = Counter(); type_year = defaultdict(Counter); topic_year = defaultdict(Counter); approach_year = defaultdict(Counter)
    tag_counts = defaultdict(Counter); journals = Counter(); authors = Counter(); first_authors = Counter(); cites = []; cites_year = Counter()
    for r, s in zip(papers, index):
        y = r.get("year")
        if not y:
            continue
        by_year[y] += 1
        for ax, vals in s["tags"].items():
            for v in vals:
                tag_counts[ax][v] += 1
                (type_year if ax == "type" else topic_year if ax == "topic" else approach_year)[y][v] += 1
        if r.get("journal") and r.get("kind") == "article":
            journals[r["journal"]] += 1
        au = s["au"]
        if au:
            first_authors[au[0]] += 1
            for a in set(au):
                authors[a] += 1
        if r.get("cited_by_count") is not None:
            cites.append((r["cited_by_count"], s["id"], s["t"], s["a"], y, r.get("journal") or ""))
            cites_year[y] += r["cited_by_count"]
    cites.sort(reverse=True)
    years = sorted(by_year)

    def series(d):
        keys = sorted({k for y in d for k in d[y]}, key=lambda k: -sum(d[y][k] for y in d))
        return {"keys": keys, "rows": [[y] + [d[y][k] for k in keys] for y in years]}
    return {"n": len(papers), "years": years, "per_year": [by_year[y] for y in years], "cites_per_year": [cites_year[y] for y in years],
            "type_by_year": series(type_year), "topic_by_year": series(topic_year), "approach_by_year": series(approach_year),
            "tag_counts": {ax: c.most_common() for ax, c in tag_counts.items()}, "top_journals": journals.most_common(30),
            "top_authors": authors.most_common(60), "top_first_authors": first_authors.most_common(30),
            "most_cited": [{"cites": c, "id": i, "t": t, "a": a, "y": y, "j": j} for c, i, t, a, y, j in cites[:40]],
            "n_journals": len(journals), "n_authors": len(authors), "total_cites": sum(c for c, *_ in cites), "n_with_cites": len(cites)}


def rss(items):
    now = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>', f"<title>CANlab: new papers</title><link>{SITE_URL}/</link>",
           "<description>New publications from the Cognitive and Affective Neuroscience Lab at Dartmouth.</description>", f"<lastBuildDate>{now}</lastBuildDate>"]
    for r in items:
        out.append(f"<item><title>{escape(r['t'])}</title><link>{SITE_URL}/papers/{escape(r['id'])}.html</link><guid isPermaLink=\"true\">{SITE_URL}/papers/{escape(r['id'])}.html</guid>"
                   f"<description>{escape((r['al'] + ' (' + str(r['y']) + '). ' + r['j'] + '. ' + r['s']).strip())}</description></item>")
    out.append("</channel></rss>")
    return "\n".join(out)


def main():
    papers = json.load(open(config.PAPERS))
    papers.sort(key=lambda r: (-(r.get("year") or 0), r.get("date") or "", r["id"]))
    merge_author_variants(papers)
    site = config.SITE_DATA
    shutil.rmtree(site, ignore_errors=True)
    site.mkdir(parents=True)
    tax = json.load(open(config.ROOT / "pipeline" / "taxonomy.json"))
    index = [slim(r) for r in papers]
    json.dump(index, open(site / "index.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump({r["id"]: r for r in papers}, open(site / "papers.json", "w"), ensure_ascii=False, separators=(",", ":"))
    json.dump([{"id": r["id"], "t": r["title"], "ab": r.get("abstract") or "", "kw": " ".join((r.get("keywords") or []) + (r.get("free_keywords") or [])), "au": " ".join(r["authors"]), "j": r.get("journal") or ""} for r in papers],
              open(site / "text.json", "w"), ensure_ascii=False, separators=(",", ":"))
    shutil.copy(config.ROOT / "pipeline" / "taxonomy.json", site / "taxonomy.json")
    for name in ("people.json", "research.json", "resources.json", "join.json", "news_posts.json", "news.json", "candidates.json", "events.json"):
        src = config.DATA / name
        if src.exists():
            shutil.copy(src, site / name)
    years = sorted({r["year"] for r in papers if r.get("year")})
    stats = {"updated": time.strftime("%Y-%m-%d"), "n": len(papers), "years": years, "y0": years[0] if years else None, "y1": years[-1] if years else None,
             "n_pdf": sum(1 for r in papers if pdf_link(r)), "n_tagged": sum(1 for r in papers if r.get("tags")), "n_cites": sum(r.get("cited_by_count") or 0 for r in papers),
             "n_people": len(json.load(open(config.DATA / "people.json"))) if (config.DATA / "people.json").exists() else 0,
             "n_candidates": len(json.load(open(config.CANDIDATES))) if config.CANDIDATES.exists() else 0}
    json.dump(stats, open(site / "stats.json", "w"), indent=1)
    json.dump(bibliometrics(papers, index), open(site / "bibliometrics.json", "w"), ensure_ascii=False, separators=(",", ":"))
    pdir = config.SITE / "papers"
    shutil.rmtree(pdir, ignore_errors=True)
    pdir.mkdir()
    for r, s in zip(papers, index):
        (pdir / f"{r['id']}.html").write_text(paper_page(r, s, tax, related_papers(s, index)))
    recent = sorted(index, key=lambda r: (r["added"], r["d"] or str(r["y"])), reverse=True)[:config.FEED_CAP]
    (config.SITE / "feed.xml").write_text(rss(recent))
    today = time.strftime("%Y-%m-%d")
    pages = [("", "weekly", "1.0"), ("publications.html", "daily", "0.9"), ("research.html", "monthly", "0.8"), ("people.html", "monthly", "0.8"), ("news.html", "daily", "0.7"),
             ("resources.html", "monthly", "0.7"), ("network.html", "weekly", "0.5"), ("bibliometrics.html", "weekly", "0.5"), ("join.html", "monthly", "0.6"), ("about.html", "monthly", "0.5")]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += [f"<url><loc>{SITE_URL}/{u}</loc><lastmod>{today}</lastmod><changefreq>{f}</changefreq><priority>{p}</priority></url>" for u, f, p in pages]
    sm += [f"<url><loc>{SITE_URL}/papers/{r['id']}.html</loc><lastmod>{r.get('date_added') or today}</lastmod><changefreq>monthly</changefreq><priority>0.6</priority></url>" for r in papers]
    sm.append("</urlset>")
    (config.SITE / "sitemap.xml").write_text("\n".join(sm))
    (config.SITE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nDisallow: /data/\nSitemap: {SITE_URL}/sitemap.xml\n")
    print(f"site data: {len(index)} papers, {stats['n_tagged']} tagged, {stats['n_pdf']} with PDF; {len(papers)} paper pages")


if __name__ == "__main__":
    main()
