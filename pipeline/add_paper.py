"""Add a paper to data/papers.json from an identifier (for lab members; run it locally, from Claude Code, or from the
"Add a paper" GitHub Actions workflow, which opens a pull request for review).

  python -m pipeline.add_paper 10.1101/2026.01.02.123456             DOI (or https://doi.org/...)
  python -m pipeline.add_paper https://www.biorxiv.org/content/10.1101/...   bioRxiv / medRxiv page
  python -m pipeline.add_paper arXiv:2501.01234                      arXiv id or URL
  python -m pipeline.add_paper 41234567                              PubMed id (or pubmed URL, or PMC1234567)
  python -m pipeline.add_paper --from-json rec.json                  hand-made record (in press, proofs, chapters)

Options: --pdf PATH_OR_URL (else the open-access PDF is fetched when there is one), --status "in press"|preprint|
published, --code URL / --data URL / --paradigm URL (repeatable), --tags-json FILE (tags written by hand or by Claude
Code, same JSON shape as the model's output), --no-llm, --by NAME, --force (skip the lab-author check), --dry-run,
--summary FILE (markdown report, used as the pull-request body).

What it does: resolves metadata (OpenAlex, then Crossref, plus PubMed for the abstract), checks that the PI is an
author, refuses duplicates, and, when the new paper is the published version of a preprint already in the database,
merges it into that record (the preprint DOI becomes a "Preprint" link). A paper waiting in the daily-search queue
(data/candidates.json) is promoted instead of re-fetched. The PDF goes to site/pdf/<id>.pdf (or
site/pdf/author_manuscripts/ for PubMed Central manuscripts), tagging uses the full text when there is a PDF, and
GitHub repositories cited in the PDF are listed in the report as suggestions (never added automatically).
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from datetime import date
from pathlib import Path

import requests

from . import config, db, openalex, refs

UA = {"User-Agent": f"{config.TOOL_NAME} add-paper/1.0"}
PREPRINT_PREFIXES = {"10.1101": "bioRxiv", "10.64898": "bioRxiv", "10.48550": "arXiv", "10.31234": "PsyArXiv", "10.31219": "OSF Preprints",
                     "10.21203": "Research Square", "10.2139": "SSRN", "10.20944": "Preprints.org", "10.36227": "TechRxiv"}
GENERIC_REPOS = {"canlab/canlabcore", "canlab/mediationtoolbox", "canlab/neuroimaging_pattern_masks", "canlab/canlab_help_examples", "canlab/robusttoolbox",
                 "canlab/canlab_mkda_metaanalysis", "canlab/lindquist_dynamic_correlation", "canlab/canlab_single_trials", "nilearn/nilearn", "nipy/nibabel",
                 "scikit-learn/scikit-learn", "cosanlab/nltools", "poldracklab/fmriprep", "nipreps/fmriprep", "spm/spm12"}
PDF_DIR = config.SITE / "pdf"


# ----------------------------------------------------------------------------- identifiers
def parse_identifier(s):
    """-> ("doi"|"pmid"|"pmcid", value)"""
    s = s.strip()
    m = re.search(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:)\s*(\d{4}\.\d{4,5})", s, re.I)
    if m:
        return "doi", f"10.48550/arXiv.{m.group(1)}"
    m = re.search(r"(10\.\d{4,9}/[^\s?#]+)", urllib.parse.unquote(s))
    if m:
        doi = re.sub(r"(v\d+)?(\.full(\.pdf)?|\.abstract|\.pdf)?$", "", m.group(1).rstrip("/.")) if re.match(r"10\.(1101|64898)/", m.group(1)) else m.group(1).rstrip("/.")
        return "doi", doi.lower()
    m = re.search(r"(PMC\d+)", s, re.I)
    if m:
        return "pmcid", m.group(1).upper()
    m = re.search(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|pmid[:\s]*)?(\d{6,9})\b", s, re.I)
    if m:
        return "pmid", m.group(1)
    raise SystemExit(f"Could not recognise an identifier in {s!r} (give a DOI, arXiv id, PubMed id or PMC id).")


# ----------------------------------------------------------------------------- metadata
def initials(given):
    return " ".join(p[0] + "." for p in re.split(r"[\s-]+", given or "") if p)


def crossref(doi):
    r = requests.get("https://api.crossref.org/works/" + urllib.parse.quote(doi), headers=UA, timeout=40)
    if r.status_code != 200:
        return None
    m = r.json()["message"]
    auth = [(a["family"] + ", " + initials(a.get("given", ""))).strip(", ") if a.get("family") else a.get("name", "") for a in m.get("author") or []]
    parts = ((m.get("published") or m.get("issued") or m.get("posted") or {}).get("date-parts") or [[None]])[0]
    ds = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p)
    abstract = re.sub(r"<[^>]+>", " ", m.get("abstract") or "")
    abstract = re.sub(r"\s+", " ", re.sub(r"^\s*Abstract\s*", "", abstract)).strip()
    posted = m.get("type") == "posted-content"
    return {"title": re.sub(r"\s+", " ", (m.get("title") or [""])[0]).strip(), "authors": [a for a in auth if a],
            "year": parts[0], "date": ds, "status": "preprint" if posted else "published", "kind": "article",
            "journal": (m.get("container-title") or [""])[0] or (m.get("institution") or [{}])[0].get("name", "") or "",
            "volume": m.get("volume"), "issue": m.get("issue"), "pages": m.get("page") or m.get("article-number"),
            "doi": doi.lower(), "abstract": abstract, "landing_url": m.get("URL"), "links": [], "source": "crossref", "keywords": []}


def pubmed_extra(pmid=None, pmcid=None, doi=None):
    try:
        from . import pubmed
        if not pmid:
            term = f"{doi}[AID]" if doi else f"{pmcid}[PMCID]"
            ids = pubmed.search(term)
            pmid = ids[0] if ids else None
        recs = pubmed.fetch([pmid]) if pmid else []
        return recs[0] if recs else None
    except Exception as e:  # noqa: BLE001
        print("PubMed lookup failed:", str(e)[:200])
        return None


def fetch_metadata(kind, value):
    rec = None
    try:
        w = openalex.by_doi(value) if kind == "doi" else (openalex.by_pmid(value) if kind == "pmid" else None)
        rec = openalex.to_record(w) if w else None
    except Exception as e:  # noqa: BLE001
        print("OpenAlex lookup failed:", str(e)[:160])
    if not rec and kind == "doi":
        try:
            rec = crossref(value)
        except Exception as e:  # noqa: BLE001
            print("Crossref lookup failed:", str(e)[:160])
    pm = pubmed_extra(pmid=rec.get("pmid") if rec else (value if kind == "pmid" else None), pmcid=value if kind == "pmcid" else None,
                      doi=(rec or {}).get("doi") or (value if kind == "doi" else None))
    if not rec and pm:
        rec = {"title": pm.get("title", ""), "authors": [a if isinstance(a, str) else a.get("family", "") for a in pm.get("authors") or []],
               "year": pm.get("year"), "date": pm.get("date") or "", "status": "published", "kind": "article", "journal": pm.get("journal") or "",
               "doi": (pm.get("doi") or "").lower() or None, "links": [], "source": "pubmed", "keywords": (pm.get("keywords") or [])[:10]}
    if not rec:
        raise SystemExit(f"No metadata found for {value} in OpenAlex, Crossref or PubMed.")
    if pm:
        rec["pmid"] = rec.get("pmid") or pm.get("pmid")
        rec["pmcid"] = rec.get("pmcid") or pm.get("pmcid")
        if len(pm.get("abstract") or "") > len(rec.get("abstract") or ""):
            rec["abstract"], rec["abstract_source"] = pm["abstract"], "pubmed"
    if rec.get("doi"):
        prefix = rec["doi"].split("/")[0]
        if prefix in PREPRINT_PREFIXES:
            rec["status"] = "preprint"
            if not rec.get("journal") or rec["journal"].lower() in ("preprint", "cold spring harbor laboratory"):
                rec["journal"] = PREPRINT_PREFIXES[prefix]
        rec["landing_url"] = rec.get("landing_url") or f"https://doi.org/{rec['doi']}"
    rec["journal"] = refs.canon(rec.get("journal") or "", rec)
    return rec


def short_names(authors):
    out = []
    for a in authors:
        if "," in a:
            sur, ini = a.split(",", 1)
            out.append(f"{sur.strip()} {''.join(ch for ch in ini if ch.isupper())}".strip())
        else:
            out.append(a)
    return out


# ----------------------------------------------------------------------------- PDF
def get_pdf(src):
    """Local path or URL -> bytes (only if it really is a PDF)."""
    if not src:
        return None, None
    if re.match(r"https?://", src):
        try:
            r = requests.get(src, headers={**UA, "Accept": "application/pdf"}, timeout=90, allow_redirects=True)
        except Exception as e:  # noqa: BLE001
            print("PDF download failed:", str(e)[:200]); return None, src
        data = r.content if r.status_code == 200 else b""
    else:
        p = Path(src).expanduser()
        data = p.read_bytes() if p.exists() else b""
    if not data.startswith(b"%PDF"):
        print(f"Not a PDF (skipped): {src}")
        return None, src
    if len(data) > 60_000_000:
        print(f"PDF over 60 MB (skipped): {src}")
        return None, src
    return data, src


def pdf_text(path):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # older PyMuPDF
        except ImportError:
            print("PyMuPDF not installed: tagging will use the abstract (pip install pymupdf).")
            return ""
    d = pymupdf.open(str(path))
    return "\n".join(pg.get_text() for pg in d)


def github_repos(text):
    """Paper-specific GitHub repos cited in the text, verified to exist and be public."""
    joined = re.sub(r"-\s*\n\s*", "-", text)
    joined = re.sub(r"(github\.com/[\w.\-]*)\s*\n\s*([\w.\-/]+)", r"\1\2", joined)
    found = []
    for owner, repo in re.findall(r"github\.com/([A-Za-z0-9_.\-]+)/([A-Za-z0-9_.\-]+)", joined):
        repo = re.sub(r"\.git$|[.\-]+$", "", repo)
        key = f"{owner}/{repo}"
        if key.lower() in GENERIC_REPOS or key in found:
            continue
        found.append(key)
    ok = []
    for key in found[:15]:
        if shutil.which("git"):
            r = subprocess.run(["git", "ls-remote", "-q", f"https://github.com/{key}.git", "HEAD"], capture_output=True, timeout=30,
                               env={"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"})
            if r.returncode != 0:
                continue
        ok.append("https://github.com/" + key)
    return ok


# ----------------------------------------------------------------------------- main
def lab_author(rec):
    return any(a.split(",")[0].strip().lower() in config.LAB_AUTHOR_SURNAMES for a in rec.get("authors") or [])


def merge_published(old, new):
    """The published version of a preprint already in the database: update the record, keep the preprint as a link."""
    if old.get("doi") and old["doi"] != new.get("doi"):
        old["preprint_doi"] = old.get("preprint_doi") or old["doi"]
        venue = old.get("journal") or "preprint"
        old.setdefault("links", []).append({"type": "preprint", "label": f"Preprint ({venue} {old.get('year') or ''})".replace(" )", ")"), "url": f"https://doi.org/{old['doi']}"})
    for k in ("title", "authors", "authors_short", "year", "date", "status", "kind", "journal", "volume", "issue", "pages", "doi", "pmid", "pmcid", "openalex_id", "landing_url", "oa_url"):
        if new.get(k):
            old[k] = new[k]
    if len(new.get("abstract") or "") > len(old.get("abstract") or ""):
        old["abstract"] = new["abstract"]
    for l in old.get("links", []):
        if l["type"] == "pdf" and "preprint" not in l.get("label", "").lower():
            l["label"] = "PDF (preprint version)"
    old["citation"] = refs.make_citation(old)
    return old


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("identifier", nargs="?")
    ap.add_argument("--from-json")
    ap.add_argument("--pdf")
    ap.add_argument("--status", choices=["published", "in press", "preprint", "under review"])
    ap.add_argument("--code", action="append", default=[])
    ap.add_argument("--data", action="append", default=[])
    ap.add_argument("--paradigm", action="append", default=[])
    ap.add_argument("--tags-json")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--by", default="")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--summary")
    a = ap.parse_args(argv)
    if not a.identifier and not a.from_json:
        ap.error("give an identifier or --from-json")

    papers = db.load_papers(); cands = db.load_json(config.CANDIDATES, [])
    by_doi, by_pmid, by_title = db.index(papers)
    notes, today = [], date.today().isoformat()

    # 1. the new record
    queued = None
    if a.from_json:
        rec = json.load(open(a.from_json))
        missing = [k for k in ("title", "authors", "year") if not rec.get(k)]
        if missing:
            raise SystemExit(f"--from-json record lacks {missing}")
        rec.setdefault("kind", "article"); rec.setdefault("status", "published"); rec.setdefault("links", []); rec["source"] = rec.get("source") or "manual"
    else:
        kind, value = parse_identifier(a.identifier)
        for c in cands:
            if (kind == "doi" and (c.get("doi") or "").lower() == value) or (kind == "pmid" and str(c.get("pmid")) == value):
                queued = c; break
        rec = dict(queued) if queued else fetch_metadata(kind, value)
        if queued:
            rec.pop("candidate", None); notes.append("Promoted from the daily-search queue (candidates.json).")
    if a.status:
        rec["status"] = a.status
    if rec.get("status") == "preprint":
        rec["kind"] = "article"  # the site marks preprints by status; kind stays article like the existing records
    rec["authors_short"] = rec.get("authors_short") or short_names(rec["authors"])
    if not lab_author(rec) and not a.force:
        raise SystemExit(f"Tor Wager is not among the authors of '{rec['title'][:80]}' ({len(rec['authors'])} authors). Use --force if the author list is wrong.")

    # 2. duplicates, or a preprint's published version
    old = db.find(rec, by_doi, by_pmid, by_title)
    merged = False
    if old:
        if old.get("status") == "preprint" and rec.get("status") in ("published", "in press") and old.get("doi") != rec.get("doi"):
            merge_published(old, rec); rec = old; merged = True
            notes.append(f"Published version of the preprint already listed as `{old['id']}`: record updated, preprint kept as a link.")
        else:
            raise SystemExit(f"Already in the database as {old['id']}: {old['title'][:90]}")
    else:
        rec["id"] = queued["id"] if queued else db.make_id(rec["authors"][0] if rec["authors"] else "", rec.get("year"), rec["title"], {r["id"] for r in papers})
        rec["date_added"] = today
        rec["source"] = (rec.get("source") or "manual") + (f" (added by {a.by})" if a.by else "")
    pid = rec["id"]

    # 3. links
    for typ, urls, label in (("code", a.code, "Code (GitHub)"), ("data", a.data, "Data (GitHub)"), ("paradigm", a.paradigm, "Paradigm (GitHub)")):
        for u in urls:
            if not any(l["url"].rstrip("/") == u.rstrip("/") for l in rec.get("links", [])):
                rec.setdefault("links", []).append({"type": typ, "label": label if "github.com" in u else typ.capitalize(), "url": u})

    # 4. PDF (given, else open access)
    full_text, suggestions = "", []
    data, src = get_pdf(a.pdf or rec.get("oa_url"))
    if data:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
        full_text = pdf_text(tmp.name)
        am = bool(re.search(r"HHS Public Access|Author manuscript", full_text[:4000], re.I))
        target = (PDF_DIR / "author_manuscripts" if am else PDF_DIR) / f"{pid}.pdf"
        rel = target.relative_to(config.SITE).as_posix()
        if not a.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(tmp.name, target)
        rec["links"] = [l for l in rec.get("links", []) if l["type"] != "pdf"]  # a new PDF replaces any earlier one (incl. a merged preprint's)
        rec["links"].insert(0, {"type": "pdf", "label": "PDF", "url": rel, "url_original": src if re.match(r"https?://", src or "") else rel,
                                "version": "author_manuscript" if am else "publisher"})
        rec["has_pdf"] = True
        notes.append(f"PDF saved to `site/{rel}`" + (" (PubMed Central author manuscript)." if am else "."))
        suggestions = [u for u in github_repos(full_text) if not any(l["url"].rstrip("/").lower() == u.lower() for l in rec["links"])]
    else:
        rec["has_pdf"] = bool(rec.get("has_pdf"))
        notes.append("No PDF attached" + (f" (could not use {src})" if src else "") + "; add one with --pdf when available.")

    # 5. tags
    if a.tags_json:
        from . import classify
        t = json.load(open(a.tags_json))
        classify.apply(rec, t, t.get("model") or "Claude Code (manual)", t.get("input_mode") or ("full_text" if full_text else "abstract"))
        notes.append("Tags from " + a.tags_json + ".")
    elif queued and rec.get("tags") and not full_text:
        notes.append("Kept the tags the daily search assigned.")
    elif not a.no_llm:
        try:
            from . import classify
            classify.classify_record(rec, full_text=full_text or None)
            notes.append(f"Tagged by {rec['classification']['model']} from the {rec['classification']['input_mode'].replace('_', ' ')}.")
        except Exception as e:  # noqa: BLE001
            notes.append(f"**Not tagged**: the model call failed ({str(e)[:160]}). Tag it by hand or re-run with an API key.")
    if not (rec.get("tags") or {}).get("type"):
        rec.setdefault("tags", {"topic": [], "approach": [], "type": []})
        notes.append("**Needs tags** before merging (no tags assigned).")

    rec["citation"] = refs.make_citation(rec)

    # 6. save
    if not a.dry_run:
        if not merged:
            papers.append(rec)
        db.save_papers(papers)
        if queued:
            db.save_json(config.CANDIDATES, [c for c in cands if c["id"] != queued["id"]])

    # 7. report
    tags = rec.get("tags") or {}
    lines = [f"### {rec['title']}", "", f"`{pid}` · {', '.join(rec['authors'][:6])}{' et al.' if len(rec['authors']) > 6 else ''} · "
             f"{rec.get('journal') or ''} {rec.get('year') or ''} · status: {rec.get('status')}", "",
             f"- DOI: {rec.get('doi') or '—'} · PMID: {rec.get('pmid') or '—'}",
             f"- Tags: topic {', '.join(tags.get('topic', [])) or '—'}; approach {', '.join(tags.get('approach', [])) or '—'}; type {', '.join(tags.get('type', [])) or '—'}",
             f"- Summary: {rec.get('summary') or '—'}"] + [f"- {n}" for n in notes]
    if suggestions:
        lines += ["", "GitHub repositories cited in the PDF (not added; add the paper-specific ones with `--code`):"] + [f"- {u}" for u in suggestions]
    report = "\n".join(lines)
    print(report)
    if a.summary:
        with open(a.summary, "a") as f:
            f.write(report + "\n\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
