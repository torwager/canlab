"""Daily worker: find new papers by the lab -> dedup -> enrich -> tag -> add to the candidates queue -> build site.

Usage: python -m pipeline.run_daily [--days N] [--dry-run] [--no-llm] [--refresh-citations N]

Sources: OpenAlex (works by the configured author ids) and PubMed (author + affiliation query). Candidates are
never added to data/papers.json automatically: they go to data/candidates.json, shown on the publications page as
"awaiting review", and are promoted with `python -m pipeline.approve <id>` (or by editing the file). Everything seen
is remembered in data/screened.json so re-running with overlapping windows is safe.
"""
import argparse
import json
import sys
import time
import traceback
from datetime import date, timedelta
from . import config, db, openalex, classify, build_site

RUNS = config.DATA / "runs"


def discover(days):
    since = (date.today() - timedelta(days=days)).isoformat()
    cands, report = {}, {}
    try:
        n = 0
        for aid in config.OPENALEX_AUTHOR_IDS:
            for w in openalex.author_works(aid, since):
                rec = openalex.to_record(w)
                if rec["title"]:
                    cands[rec["doi"] or rec["openalex_id"]] = rec; n += 1
        report["openalex"] = n
    except Exception as e:  # noqa: BLE001
        report["openalex"] = {"error": str(e)[:300]}; traceback.print_exc()
    try:
        from . import pubmed
        ids = pubmed.search(config.PUBMED_QUERY, mindate=(date.today() - timedelta(days=days)).strftime("%Y/%m/%d"), datetype="edat")
        n = 0
        for rec in pubmed.fetch(ids):
            r = {"title": rec.get("title", ""), "authors": [a if isinstance(a, str) else a.get("family", "") for a in rec.get("authors") or []],
                 "authors_short": [a if isinstance(a, str) else a.get("family", "") for a in rec.get("authors") or []],
                 "year": rec.get("year"), "date": rec.get("date") or "", "status": "published", "kind": "article", "journal": rec.get("journal") or "",
                 "doi": (rec.get("doi") or "").lower() or None, "pmid": rec.get("pmid"), "abstract": rec.get("abstract") or "", "links": [], "source": "pubmed",
                 "keywords": (rec.get("keywords") or [])[:10]}
            key = r["doi"] or ("pmid:" + str(r["pmid"]))
            if key not in cands and not any(c.get("pmid") == r["pmid"] for c in cands.values()):
                cands[key] = r; n += 1
        report["pubmed"] = n
    except Exception as e:  # noqa: BLE001
        report["pubmed"] = {"error": str(e)[:300]}
    return cands, report


def is_lab_paper(rec):
    return any(a.split(",")[0].strip().lower() in config.LAB_AUTHOR_SURNAMES for a in rec.get("authors") or [])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--refresh-citations", type=int, default=0, help="also refresh citation counts for N papers (oldest refresh first)")
    args = ap.parse_args(argv)
    t0 = time.time(); today = date.today().isoformat()
    papers = db.load_papers()
    cands_file = db.load_json(config.CANDIDATES, [])
    screened = db.load_json(config.SCREENED, {})
    by_doi, by_pmid, by_title = db.index(papers)
    existing_ids = {r["id"] for r in papers} | {c["id"] for c in cands_file}
    found, report = discover(args.days)
    new = []
    for key, rec in found.items():
        if key in screened or db.find(rec, by_doi, by_pmid, by_title) or any(db.find(rec, *db.index([c])) for c in cands_file):
            continue
        if not is_lab_paper(rec):
            screened[key] = {"date": today, "reason": "not_lab_author"}; continue
        rec["id"] = db.make_id(rec["authors"][0] if rec["authors"] else "", rec.get("year"), rec["title"], existing_ids)
        existing_ids.add(rec["id"])
        rec["citation"] = f"{', '.join(rec['authors'][:6])}{' et al.' if len(rec['authors']) > 6 else ''} ({rec.get('year')}). {rec['title']}. {rec.get('journal', '')}."
        rec["date_added"] = today; rec["candidate"] = True
        if not args.no_llm:
            try:
                classify.classify_record(rec)
            except Exception as e:  # noqa: BLE001
                print("tagging error", rec["id"], str(e)[:200], flush=True)
        screened[key] = {"date": today, "reason": "candidate", "id": rec["id"]}
        new.append(rec)
    print(f"found {len(found)}, new candidates {len(new)}; sources={json.dumps(report)}", flush=True)
    n_ref = 0
    if args.refresh_citations:
        order = sorted(papers, key=lambda r: (r.get("citations_refreshed") or "", r["id"]))[: args.refresh_citations]
        n_ref = openalex.refresh_citations(order)
        for r in order:
            r["citations_refreshed"] = today
    stats = {"date": today, "found": len(found), "new_candidates": len(new), "sources": report, "citations_refreshed": n_ref, "seconds": round(time.time() - t0)}
    print(json.dumps(stats), flush=True)
    if args.dry_run:
        return 0
    if new:
        db.save_json(config.CANDIDATES, cands_file + new)
    db.save_json(config.SCREENED, screened)
    if n_ref:
        db.save_papers(papers)
    RUNS.mkdir(parents=True, exist_ok=True)
    json.dump(stats, open(RUNS / f"{today}.json", "w"), indent=1)
    build_site.main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
