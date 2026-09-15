"""Re-tag records with the current taxonomy, limited to the ones a pattern matches.

Used when a new tag value is added (e.g. the tms/tdcs/tis stimulation tags in taxonomy 1.1.0):
re-running the whole database costs real money, so re-tag only the records that could plausibly
carry the new value, plus any that already carry a tag named with --also-tag.

    python scripts/retag.py --file data/journal_club.json --match STIM --also-tag brain_stimulation [--apply]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PATTERNS = {
    # brain / nerve stimulation of any kind
    "STIM": r"\b(tdcs|tacs|trns|tes\b|t?tis\b|temporal interference|tms\b|rtms|theta[- ]burst|itbs|ctbs|transcranial|neurostimulation|neuromodulation|deep brain stimulation|\bdbs\b|focused ultrasound|\btus\b|\bfus\b|vagus|\bvns\b|\btavns\b|spinal cord stimulation|electrical stimulation|magnetic stimulation|electroconvulsive|\bect\b|optogenetic|closed[- ]loop stimulation|intracranial stimulation)\b",
}


def blob(it):
    parts = [str(it.get(k) or "") for k in ("title", "abstract", "summary", "key_finding", "journal", "message")]
    parts += list(it.get("free_keywords") or [])
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/journal_club.json")
    ap.add_argument("--match", default="STIM", help="a key of PATTERNS, or a regex")
    ap.add_argument("--also-tag", action="append", default=[], help="re-tag records already carrying this tag id")
    ap.add_argument("--include-unresolved", action="store_true", help="also re-tag records whose title came from the Slack message")
    ap.add_argument("--apply", action="store_true", help="without this, only list what would be re-tagged")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()

    path = Path(a.file)
    store = json.loads(path.read_text())
    items = store["items"] if isinstance(store, dict) else store
    pat = re.compile(PATTERNS.get(a.match, a.match), re.I)

    todo = []
    for it in items:
        if it.get("kind", "paper") not in ("paper", "article", "chapter", "preprint", "proceedings", "other"):
            continue
        if not it.get("title") or (it.get("title_unresolved") and not a.include_unresolved):
            continue
        tagged = set((it.get("tags") or {}).get("approach") or [])
        if pat.search(blob(it)) or (tagged & set(a.also_tag)):
            todo.append(it)
    if a.limit:
        todo = todo[: a.limit]
    print(f"{len(todo)} of {len(items)} records match")
    if not a.apply:
        for it in todo[:200]:
            print(" ", it["id"], "|", (it.get("title") or "")[:90])
        return

    from pipeline.classify import classify_record

    cost, fails = 0.0, 0
    for n, it in enumerate(todo, 1):
        try:
            rec = {"id": it["id"], "title": it["title"], "authors": it.get("authors") or [], "journal": it.get("journal") or "",
                   "year": it.get("year"), "abstract": it.get("abstract") or "", "citation": it.get("citation") or ""}
            classify_record(rec)
            for k in ("tags", "summary", "key_finding", "free_keywords", "classification"):
                it[k] = rec.get(k)
            cost += ((rec.get("classification") or {}).get("usage") or {}).get("cost_usd") or 0
            fails = 0
            stim = [t for t in it["tags"]["approach"] if t in ("brain_stimulation", "tms", "tdcs", "tis")]
            print(f"{n}/{len(todo)} {it['id']}: {','.join(stim) or '-'}")
        except Exception as e:  # noqa: BLE001
            fails += 1
            print("failed", it["id"], e)
            if fails >= 3:
                path.write_text(json.dumps(store, indent=1, ensure_ascii=False) + "\n")
                raise SystemExit("tagging keeps failing; stopping so the error is visible")
        if n % 15 == 0:
            path.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    path.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    print(f"re-tagged {len(todo)} records, ${cost:.2f} -> {path}")


if __name__ == "__main__":
    main()
