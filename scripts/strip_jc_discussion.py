"""Remove lab members' words from the public journal club data (decision 2026-09-22).

- Drops each item's Slack message text and thread replies; keeps a reply count (n_comments) for sorting.
- Titles that were taken from the message (the link gave no usable title) are replaced: by the paper's real
  metadata when Crossref confirms the pasted text is a paper title, else by a neutral "Link on <site>".
  For the neutral ones the LLM summary, key finding and keywords (written from the message) are cleared too.
Run once: python scripts/strip_jc_discussion.py
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.jc_curate import crossref_title_match, message_line, neutral_title, _norm  # noqa: E402

OUT = ROOT / "data" / "journal_club.json"


def from_message(it):
    if it.get("title_unresolved"):
        return True
    line = message_line(it)
    return bool(line) and _norm(line)[:60] == _norm(it.get("title"))[:60] and not it.get("authors")


def main():
    store = json.loads(OUT.read_text())
    matched = neutral = 0
    for n, it in enumerate(store["items"], 1):
        if "comments" in it:
            it["n_comments"] = len(it.pop("comments") or [])
        if from_message(it):
            meta = crossref_title_match(message_line(it) or it.get("title"))
            time.sleep(0.5)
            if meta:
                for k, v in meta.items():
                    if v:
                        it[k] = v
                it.setdefault("publisher_url", "https://doi.org/" + meta["doi"])
                it["kind"] = "paper"
                it.pop("title_unresolved", None)
                matched += 1
            else:
                it["title"], it["title_unresolved"] = neutral_title(it), True
                for k in ("summary", "key_finding", "free_keywords"):
                    it.pop(k, None)
                neutral += 1
        it.pop("message", None)
        if n % 100 == 0:
            print(f"{n}/{len(store['items'])}", file=sys.stderr, flush=True)
    OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    print(f"confirmed by Crossref: {matched}; neutral titles: {neutral}")


if __name__ == "__main__":
    main()


def fix_titles_from_doi(before_path):
    """Second pass (2026-09-22): items WITH a DOI whose title was still the poster's message line.
    Replace the title with Crossref's title for that DOI whenever the two differ. `before_path` is a copy of
    journal_club.json from before the strip (git show <commit>:data/journal_club.json), which still holds the messages."""
    import difflib
    from pipeline.jc_curate import crossref_meta
    before = {i["id"]: i for i in json.loads(Path(before_path).read_text())["items"]}
    store = json.loads(OUT.read_text())
    fixed = checked = 0
    for it in store["items"]:
        b = before.get(it["id"])
        if not b or not it.get("doi"):
            continue
        ml = _norm(message_line(b))
        if not ml or _norm(it.get("title"))[:50] != ml[:50]:
            continue
        checked += 1
        meta = crossref_meta(it["doi"])
        time.sleep(0.4)
        if not meta or not meta.get("title"):
            it["title"], it["title_unresolved"] = neutral_title(it), True
            for k in ("summary", "key_finding", "free_keywords"):
                it.pop(k, None)
            fixed += 1
            continue
        if difflib.SequenceMatcher(None, _norm(meta["title"]), _norm(it["title"])).ratio() < 0.9:
            it["title"] = meta["title"]
            fixed += 1
    OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False))
    print(f"checked {checked} DOI items titled from the message; retitled {fixed}")
