"""Load/save the bibliography and the daily-search ledgers."""
import json
import re
import unicodedata
from . import config


def load_papers():
    return json.load(open(config.PAPERS)) if config.PAPERS.exists() else []


def save_papers(papers):
    papers.sort(key=lambda r: (-(r.get("year") or 0), r.get("date") or "", r["id"]))
    json.dump(papers, open(config.PAPERS, "w"), indent=1, ensure_ascii=False)


def load_json(path, default):
    return json.load(open(path)) if path.exists() else default


def save_json(path, obj):
    json.dump(obj, open(path, "w"), indent=1, ensure_ascii=False)


def norm_title(t):
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def make_id(first_author, year, title, existing):
    sur = unicodedata.normalize("NFKD", (first_author or "anon").split(",")[0]).encode("ascii", "ignore").decode()
    sur = re.sub(r"[^a-z0-9]", "", sur.lower()) or "anon"
    words = [w for w in re.sub(r"[^A-Za-z ]", "", title or "").split() if len(w) > 3 and w.lower() not in ("with", "from", "that", "this", "their", "during", "between", "across", "human", "brain")]
    base = f"{sur}{year or ''}{(words[0] if words else 'paper').lower()}"
    pid, n = base, 0
    while pid in existing:
        n += 1; pid = base + chr(ord("a") + n)
    return pid


def index(papers):
    by_doi = {r["doi"].lower(): r for r in papers if r.get("doi")}
    by_pmid = {str(r["pmid"]): r for r in papers if r.get("pmid")}
    by_title = {norm_title(r["title"]): r for r in papers if r.get("title")}
    return by_doi, by_pmid, by_title


def find(rec, by_doi, by_pmid, by_title):
    if rec.get("doi") and rec["doi"].lower() in by_doi:
        return by_doi[rec["doi"].lower()]
    if rec.get("pmid") and str(rec["pmid"]) in by_pmid:
        return by_pmid[str(rec["pmid"])]
    nt = norm_title(rec.get("title"))
    if nt and nt in by_title:
        return by_title[nt]
    # fuzzy: same first 8 words
    head = " ".join(nt.split()[:8])
    if head:
        for t, r in by_title.items():
            if t.startswith(head):
                return r
    return None
