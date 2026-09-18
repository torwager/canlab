"""Apply the DOI corrections reviewed from scripts/audit_dois.py (work/doi_audit.json), September 2026.

REPLACE: the record carried the DOI of a different work (a book chapter summarising the paper, a conference
abstract, an SSRN copy, a reviewer comment, a Zenodo deposit), so its journal, volume, pages, date and
citation count were wrong too; bibliographic fields are re-taken from Crossref.
ADD: the record had no DOI (so no citation count could be refreshed); fields are filled only where empty.
PREPRINT: only a preprint DOI exists; stored in preprint_doi.
Afterwards run pipeline.openalex.refresh_citations on the touched records.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REPLACE = {
    "wager2013fmribased": ("10.1056/nejmoa1204471", "23574118"),   # was a chapter in "50 Studies Every Anesthesiologist Should Know"
    "weber2019evidence": ("10.1016/j.nicl.2019.102042", None),      # was a Journal of Pain meeting abstract
    "reddan2018attenuating": ("10.1016/j.neuron.2018.10.047", None),  # was the SSRN copy
    "picard2024distributed": ("10.7554/elife.87962", None),         # was a reviewer comment on the eLife paper
    "miao2026common": ("10.1038/s41467-026-71151-2", None),         # was a Zenodo data deposit
    "gianaros2017phenotype": ("10.1161/jaha.117.006053", "28835356"),  # the old site's PMID; the other JAHA record has 1 citation
}
ADD = {
    "adams2026emotional": "10.1007/s00415-026-14117-0", "dehghani2026transcranial": "10.1097/j.pain.0000000000003851",
    "han2022effect": "10.1016/j.neuroimage.2021.118844", "amir2022testretest": "10.1016/j.jpain.2022.01.011",
    "salman2021approach": "10.1089/brain.2020.0950", "busch2021hybrid": "10.1016/j.neuroimage.2021.117975",
    "sicorello2021affective": "10.1016/j.ynirp.2021.100019", "wang2021dorsal": "10.7554/elife.69178",
    "po2020superconsistent": "10.1111/rssb.12386", "bainter2020improving": "10.1177/2515245919885617",
    "rosenberg2020behavioral": "10.1523/jneurosci.2841-19.2020", "yu2020generalizable": "10.1093/cercor/bhz326",
    "leach2020mouse": "10.1016/j.celrep.2020.108337", "matthewson2019cognitive": "10.1097/j.pain.0000000000001621",
    "lindquist2019modular": "10.1002/hbm.24528", "kragel2019emotion": "10.1126/sciadv.aaw4358",
    "woo2019falsepositive": "10.1016/j.neuroimage.2019.03.070", "price2018transition": "10.1038/s41583-018-0012-5",
    "delavega2017largescale": "10.1093/cercor/bhx204", "benedetti2005neurobiological": "10.1523/jneurosci.3458-05.2005",
    "wager2003neuroimaging": "10.3758/cabn.3.4.255", "kragel2020fmri": "10.1177/0956797621989730",
    "ashar2025pain": "10.1001/jamapsychiatry.2025.1844", "lopezsola2018transforming": "10.1097/psy.0000000000000609",
    "he2025comparing": "10.1093/cercor/bhaf189", "xzhu2018exposurebased": "10.1002/da.22816",
    "feldmannbarrett2006structure": "10.1111/j.0963-7214.2006.00411.x", "salman2020fully": "10.1109/bibm49941.2020.9313309",
    "branco2023predictability": "10.1093/med/9780197645444.003.0005",
}
PREPRINT = {"sun2026fatigue": "10.64898/2026.02.02.26345387", "bo2026spatiotemporal": "10.64898/2026.08.18.745530", "wager2004affect": "10.1101/102368"}
TITLES = {"zunhammer2019laterality": "Laterality and Stimulation Bias in Meta-analysis of Placebo Responses—Reply"}


def crossref(doi):
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "canlab-site/1.0"}), timeout=30) as r:
        return json.loads(r.read())["message"]


def fields(m):
    dp = ((m.get("published-print") or m.get("issued") or {}).get("date-parts") or [[None]])[0]
    return {"journal": (m.get("container-title") or [None])[0], "volume": m.get("volume"), "issue": m.get("issue"), "pages": m.get("page"),
            "year": dp[0], "date": "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(dp) if x)}


def main():
    exec_ns = {"__file__": str(ROOT / "scripts" / "normalize_refs.py")}
    src = (ROOT / "scripts" / "normalize_refs.py").read_text().split("\nlog = []")[0]
    exec(compile(src, "normalize_refs.py", "exec"), exec_ns)
    cite, canon = exec_ns["make_citation"], exec_ns["canon"]
    path = ROOT / "data" / "papers.json"
    papers = json.loads(path.read_text())
    by = {p["id"]: p for p in papers}
    touched = []
    for pid, (doi, pmid) in REPLACE.items():
        p, m = by[pid], crossref(doi)
        f = fields(m)
        p.update({k: v for k, v in f.items() if v})
        p["journal"] = canon(p["journal"], p)
        p["doi"], p["landing_url"], p["cited_by_count"], p["openalex_id"] = doi, "https://doi.org/" + doi, None, None
        if pmid:
            p["pmid"] = pmid
        p["citation"] = cite(p)
        touched.append(pid)
        print("replaced", pid, doi, f["journal"], f["year"])
        time.sleep(0.3)
    for pid, doi in ADD.items():
        p, m = by[pid], crossref(doi)
        f = fields(m)
        for k in ("journal", "volume", "issue", "pages"):
            if not p.get(k) and f.get(k):
                p[k] = f[k]
        p["doi"], p["cited_by_count"] = doi, None
        p["landing_url"] = p.get("landing_url") or "https://doi.org/" + doi
        p["citation"] = cite(p)
        touched.append(pid)
        print("added", pid, doi)
        time.sleep(0.3)
    for pid, doi in PREPRINT.items():
        by[pid]["preprint_doi"] = doi
    for pid, t in TITLES.items():
        by[pid]["title"] = t
        by[pid]["citation"] = cite(by[pid])
    from pipeline import openalex
    todo = [by[i] for i in touched]
    n = openalex.refresh_citations(todo)
    for p in todo:
        p["citations_refreshed"] = time.strftime("%Y-%m-%d")
    print(f"refreshed citation counts for {n} of {len(todo)}")
    path.write_text(json.dumps(papers, indent=1, ensure_ascii=False))
    for p in todo:
        print(f"  {p['id']}: {p.get('cited_by_count')}")


if __name__ == "__main__":
    main()

# Also done by hand on 2026-09-17: duff2020inferring got preprint_doi 10.1101/2020.04.01.998864 and its unverifiable count
# (1, from a wrong match) was cleared; no published DOI could be found in Crossref.
