"""Apply the PDF audit of 2026-10-09 (scripts/audit_pdfs.py + pipeline.fetch_pdfs.verify/pdf_version, then a manual
review of every flagged file). Idempotent; every change is listed here so it can be reviewed.

A. record corrections (wrong DOIs, out-of-date titles, a misspelt author)
B. PDFs that are a whole book / a whole journal treatment are cut down to the lab's own piece
C. wrong PDFs are removed: licence-to-publish forms, a letter, an erratum, a single page, another paper
D. every PDF gets an honest version label: publisher | author_manuscript | preprint
E. papers left without a published PDF are re-searched (pipeline.fetch_pdfs), published versions first
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pymupdf  # noqa: E402
import requests  # noqa: E402

from pipeline import fetch_pdfs, refs  # noqa: E402

PAPERS = ROOT / "data" / "papers.json"
SITE = ROOT / "site"

FIX = {  # A
    "chen2026modalityspecific": {"title": "Modality-specific reactive and predictive responses in the human superior colliculus", "doi": "10.1038/s41593-026-02480-0", "journal": "Nature Neuroscience", "status": "published"},
    "ashar2022pain": {"title": "Effect of Pain Reprocessing Therapy vs Placebo and Usual Care for Patients With Chronic Back Pain: A Randomized Clinical Trial"},
    "harrison2021investigating": {"title": "Investigating the specificity of the neurologic pain signature against breathlessness and finger opposition"},
    "kohoutova2020interpreting": {"title": "Toward a unified framework for interpreting machine-learning models in neuroimaging"},
    "guevarra2020placebos": {"title": "Placebos without deception reduce self-report and neural measures of emotional distress"},
    "duff2020inferring": {"title": "Inferring pain experience in infants using quantitative whole-brain functional MRI signatures: a cross-sectional, observational study", "doi": "10.1016/s2589-7500(20)30168-0"},
    "losin2020neural": {"doi": "10.1038/s41562-020-0819-8"},           # was a data-repository DOI
    "yamamoto2015influence": {"doi": "10.1016/j.drugalcdep.2014.12.026"},  # was a meeting abstract
    "yarkoni2015interactions": {"doi": "10.7717/peerj.1089", "preprint_doi": "10.7287/peerj.preprints.1182v1"},
    "wager2018pinpointing": {"title": "The long search for the pain gene", "doi": "10.1038/d41586-018-04560-z", "pages": "308"},
    "koban2011predictors": {"doi": "10.1016/b978-0-12-397928-5.00010-6"},
}
AUTHOR_FIX = {"slyvester2003switching": ("Slyvester", "Sylvester")}

EXTRACT = {  # B: 1-based inclusive page ranges of the lab's own piece
    "branco2023predictability": (84, 102),   # chapter 2.1 of the 409-page book
    "chang2015challenges": (26, 27),         # commentary inside the BBS treatment of Kalisch et al.
    "lindquist2012what": (52, 82),           # authors' response inside the BBS treatment
}

WRONG = {  # C
    "miao2026common": "Nature Communications licence-to-publish form",
    "koban2011predictors": "a different paper (Wager et al. 2011, J Neurosci)",
    "davis2020discovery": "a one-page letter, not the review",
    "speer2023multivariate": "only the first page",
    "ashar2021effects": "the journal's erratum, not the paper",
}

VERSION = {  # D: manual judgements where the first page does not say (scans, typeset chapters, proceedings)
    **{i: "publisher" for i in ["burke2026harnessing", "taylor2026measuring", "vase2025opportunities", "kragel2019emotion", "roy2017neuromatrix",
                                "wager2015using", "atlas2009neural", "vansnellenberg2009cognitive", "wager2007placebo", "etkin2007functional",
                                "wager2003neuroimaging", "duff2020inferring", "link2011past", "jung2023divergent", "plassmann2013expectancies",
                                "buhle2010using", "wager2006need", "wager2001life", "zunhammer2019laterality", "kalisch2017resilience",
                                "woo2015predictive", "branco2023predictability", "chang2015challenges", "lindquist2012what",
                                "noesteinmuller2025reply", "noesteinmuller2024reply", "wager2018pinpointing", "kwon2026convergent",
                                "picard2024distributed", "englert2026functional"]}  # eLife versions of record print "Preprint posted",
    **{i: "author_manuscript" for i in ["liu2026mitoception", "he2025comparing", "bott2025exploring", "wager2024look", "ashar2024openlabel",
                                        "amir2022testretest", "botviniknezerr2023advancing", "lindquist2014principles", "jonides2003modules",
                                        "hernandez2002introduction", "jonides2002neuroimaging", "murillo2026gray", "cremers2015altered",
                                        "kang2014bayesian", "woo2014separate", "lopezsola2014altered", "wager2008prefrontalsubcortical",
                                        "wager2011essentials", "wagertd2009essentials"]},
}
LABEL = {"publisher": "PDF", "author_manuscript": "PDF (author manuscript)", "preprint": "PDF (preprint)"}


def pdf_of(p):
    return next((l for l in p.get("links", []) if l.get("type") == "pdf"), None)


def main():
    papers = json.loads(PAPERS.read_text())
    by = {p["id"]: p for p in papers}
    log = []

    for pid, f in FIX.items():  # A
        p = by[pid]
        for k, v in f.items():
            if p.get(k) != v:
                log.append(f"{pid}: {k} {p.get(k)!r} -> {v!r}")
                p[k] = v
        if "doi" in f:
            p["landing_url"], p["cited_by_count"] = "https://doi.org/" + f["doi"], None
            p.pop("openalex_id", None)
        p["citation"] = refs.make_citation(p)
    for pid, (a, b) in AUTHOR_FIX.items():
        p = by[pid]
        p["authors"] = [x.replace(a, b) for x in p["authors"]]
        p["authors_short"] = [x.replace(a, b) for x in p.get("authors_short", [])]
        p["citation"] = refs.make_citation(p)
        log.append(f"{pid}: author {a} -> {b}")

    for pid, (start, end) in EXTRACT.items():  # B
        path = SITE / pdf_of(by[pid])["url"]
        d = pymupdf.open(path)
        if d.page_count > end - start + 1:
            out = pymupdf.open()
            out.insert_pdf(d, from_page=start - 1, to_page=end - 1)
            data = out.tobytes(garbage=3, deflate=True)
            d.close()
            path.write_bytes(data)
            log.append(f"{pid}: cut to pages {start}-{end}")

    for pid, why in WRONG.items():  # C
        p = by[pid]
        l = pdf_of(p)
        if l and not l["url"].startswith("http"):
            f = SITE / l["url"]
            if f.exists():  # each one checked by hand
                f.unlink()
                p["links"] = [x for x in p["links"] if x is not l]
                p["has_pdf"] = False
                p.pop("pdf_search", None)
                log.append(f"{pid}: removed wrong PDF ({why})")

    for p in papers:  # D
        l = pdf_of(p)
        if not l or l["url"].startswith("http") or not (SITE / l["url"]).exists():
            continue
        v = VERSION.get(p["id"]) or fetch_pdfs.pdf_version((SITE / l["url"]).read_bytes(), p)
        if v == "unknown":
            v = l.get("version") or "publisher"
        if l.get("version") != v or l.get("label") != LABEL[v]:
            log.append(f"{p['id']}: version {l.get('version')} -> {v}")
            l["version"], l["label"] = v, LABEL[v]

    PAPERS.write_text(json.dumps(papers, indent=1, ensure_ascii=False))

    # E: re-search. Missing PDFs: any acceptable version. Manuscripts/preprints of published papers: publisher only.
    sess = requests.Session()
    sess.headers.update({"User-Agent": fetch_pdfs.BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})
    today = time.strftime("%Y-%m-%d")
    for p in papers:
        l = pdf_of(p)
        if p.get("status") == "preprint" or (p.get("journal") or "").lower() in ("biorxiv", "medrxiv", "psyarxiv"):
            continue
        if l and l.get("version") == "publisher":
            continue
        if not p.get("doi") and l:
            continue
        old = (SITE / l["url"]) if l and not l["url"].startswith("http") else None
        result, tried = fetch_pdfs.process(p, sess, want_published=bool(l))
        if result.startswith("found"):
            new = SITE / pdf_of(p)["url"]
            if old and old.exists() and old.resolve() != new.resolve():
                old.unlink()
            log.append(f"{p['id']}: {'upgraded' if l else 'attached'} {result}")
        p["pdf_search"] = {"last": today, "result": result if result.startswith("found") else ("no-published-version" if l else "not-found"), "tried": tried[:12]}
        print(f"  {p['id']}: {result} ({', '.join(tried[:6])})", flush=True)
        time.sleep(1)

    PAPERS.write_text(json.dumps(papers, indent=1, ensure_ascii=False))
    fetch_pdfs.write_report(papers)
    (ROOT / "work").mkdir(exist_ok=True)
    (ROOT / "work" / "pdf_audit_changes.txt").write_text("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
