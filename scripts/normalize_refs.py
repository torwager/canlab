"""Normalize journal names and regenerate every citation in one style (APA-like), writing a change log to updated_references.txt.

Style: Authors (Year). Title. Journal, Volume(Issue), Pages. https://doi.org/DOI
Chapters: Authors (Year). Title. In Book/Editors. Pages.   Preprints: Authors (Year). Title. bioRxiv. https://doi.org/DOI
"""
import json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
papers = json.load(open(ROOT / "data" / "papers.json"))

JOURNALS = {"neuroimage": "NeuroImage", "pain": "Pain", "journal of pain": "The Journal of Pain", "j pain": "The Journal of Pain", "the lancet. psychiatry": "The Lancet Psychiatry", "lancet psychiatry": "The Lancet Psychiatry",
            "nat commun": "Nature Communications", "nature communications": "Nature Communications", "nat neurosci": "Nature Neuroscience", "j neurosci": "The Journal of Neuroscience", "journal of neuroscience": "The Journal of Neuroscience",
            "proceedings of the national academy of sciences of the united states of america": "Proceedings of the National Academy of Sciences", "pnas": "Proceedings of the National Academy of Sciences", "proc natl acad sci u s a": "Proceedings of the National Academy of Sciences",
            "cereb cortex": "Cerebral Cortex", "soc cogn affect neurosci": "Social Cognitive and Affective Neuroscience", "scan": "Social Cognitive and Affective Neuroscience", "hum brain mapp": "Human Brain Mapping",
            "neuroimage: clinical": "NeuroImage: Clinical", "neuroimage clin": "NeuroImage: Clinical", "biological psychiatry: cognitive neuroscience and neuroimaging": "Biological Psychiatry: Cognitive Neuroscience and Neuroimaging", "biol psychiatry cogn neurosci neuroimaging": "Biological Psychiatry: Cognitive Neuroscience and Neuroimaging",
            "neurosci biobehav rev": "Neuroscience & Biobehavioral Reviews", "neuroscience and biobehavioral reviews": "Neuroscience & Biobehavioral Reviews", "trends cogn sci": "Trends in Cognitive Sciences", "cogn affect behav neurosci": "Cognitive, Affective, & Behavioral Neuroscience",
            "cognitive, affective, and behavioral neuroscience": "Cognitive, Affective, & Behavioral Neuroscience", "plos biol": "PLOS Biology", "plos biology": "PLOS Biology", "plos one": "PLOS ONE", "plos computational biology": "PLOS Computational Biology", "plos comput biol": "PLOS Computational Biology",
            "j cogn neurosci": "Journal of Cognitive Neuroscience", "psychol sci": "Psychological Science", "psychosom med": "Psychosomatic Medicine", "curr biol": "Current Biology", "current biology": "Current Biology", "jama psychiatry": "JAMA Psychiatry", "eur j pain": "European Journal of Pain",
            "nature reviews neuroscience": "Nature Reviews Neuroscience", "nature reviews. neuroscience": "Nature Reviews Neuroscience", "nat rev neurosci": "Nature Reviews Neuroscience", "nature human behaviour": "Nature Human Behaviour", "nat hum behav": "Nature Human Behaviour",
            "perspect psychol sci": "Perspectives on Psychological Science", "behav brain sci": "Behavioral and Brain Sciences", "front psychol": "Frontiers in Psychology", "frontiers in psychology": "Frontiers in Psychology", "sci rep": "Scientific Reports", "scientific reports": "Scientific Reports",
            "the journal of neuroscience : the official journal of the society for neuroscience": "The Journal of Neuroscience", "nature medicine": "Nature Medicine", "nat med": "Nature Medicine", "elife": "eLife", "j neurophysiol": "Journal of Neurophysiology", "biorxiv": "bioRxiv", "medrxiv": "medRxiv", "psyarxiv": "PsyArXiv"}


def journal_from_citation(c):
    """Journal text between the title sentence and the volume, for records where the old page had no italic marker."""
    m = re.search(r"\)\.?\s+[^.]+\.\s+([A-Z][A-Za-z&:,\- ]{3,80}?)[\.,]\s*\d", c or "")
    return m.group(1).strip() if m else ""


def canon(j, rec):
    j = re.sub(r"\s+", " ", (j or "").replace("&amp;", "&")).strip(" .,")
    if j.lower() in ("", "the", "et al", "et al."):
        j = journal_from_citation(rec.get("citation")) or ""
    key = j.lower().strip()
    if key in JOURNALS:
        return JOURNALS[key]
    # Title Case the all-caps / all-lower variants
    if j.isupper() or j.islower():
        small = {"of", "and", "in", "the", "for", "on", "&", "de", "a", "an"}
        j = " ".join(w if i and w.lower() in small else (w[0].upper() + w[1:].lower() if w[0].isalpha() else w) for i, w in enumerate(j.split()))
        return JOURNALS.get(j.lower(), j)
    return j


def author_apa(a):
    return a


def authors_line(auth):
    auth = [a for a in auth if a]
    if not auth:
        return ""
    if len(auth) > 20:
        return ", ".join(auth[:19]) + ", … " + auth[-1]
    if len(auth) == 1:
        return auth[0]
    return ", ".join(auth[:-1]) + ", & " + auth[-1]


def pages_str(p):
    p = (p or "").strip()
    return p.replace("--", "–").replace("-", "–") if p else ""


def make_citation(r):
    y = r.get("year") or "n.d."
    st = r.get("status")
    year = "in press" if st == "in press" else ("under review" if st == "under review" else str(y))
    title = (r.get("title") or "").strip().rstrip(".")
    au = authors_line(r.get("authors") or []) + (", et al." if r.get("authors_truncated") else "")
    doi = f" https://doi.org/{r['doi']}" if r.get("doi") else ""
    kind = r.get("kind")
    if kind == "chapter":
        book = (r.get("journal") or "").strip().rstrip(".")
        pg = pages_str(r.get("pages"))
        return f"{au} ({year}). {title}. In {book}{', pp. ' + pg if pg else ''}.{doi}".replace("..", ".")
    if kind == "preprint" or st == "preprint":
        venue = r.get("journal") or "Preprint"
        return f"{au} (preprint). {title}. {venue}.{doi}"
    if kind == "proceedings":
        venue = (r.get("journal") or "").strip().rstrip(".")
        pg = pages_str(r.get("pages"))
        return f"{au} ({year}). {title}. {venue}{', ' + pg if pg else ''}.{doi}"
    venue = r.get("journal") or ""
    vol = r.get("volume") or ""
    iss = r.get("issue") or ""
    pg = pages_str(r.get("pages"))
    tail = ""
    if vol:
        tail = f", {vol}" + (f"({iss})" if iss else "") + (f", {pg}" if pg else "")
    elif pg:
        tail = f", {pg}"
    return f"{au} ({year}). {title}. {venue}{tail}.{doi}".replace(" .", ".").replace("..", ".")


log = []
for r in papers:
    old_j, old_c = r.get("journal") or "", r.get("citation") or ""
    r["journal"] = canon(old_j, r)
    r["citation_original"] = r.get("citation_original") or old_c
    r["citation"] = make_citation(r)
    changes = []
    if r["journal"] != old_j:
        changes.append(f"journal: '{old_j}' -> '{r['journal']}'")
    if r["citation"] != old_c:
        changes.append("citation restyled")
    if changes:
        log.append(f"{r['id']}: " + "; ".join(changes))
json.dump(papers, open(ROOT / "data" / "papers.json", "w"), indent=1, ensure_ascii=False)
print(len(log), "records changed")
