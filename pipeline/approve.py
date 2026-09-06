"""Promote candidates from data/candidates.json into data/papers.json (or reject them).

  python -m pipeline.approve <id> [<id> ...]        approve
  python -m pipeline.approve --reject <id> [...]    drop from the queue (remembered in screened.json)
  python -m pipeline.approve --list                 show the queue
"""
import sys
from datetime import date
from . import config, db


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    cands = db.load_json(config.CANDIDATES, [])
    if not argv or argv == ["--list"]:
        for c in cands:
            print(f"{c['id']:40s} {c.get('year')}  {c['title'][:80]}")
        print(f"{len(cands)} candidates"); return 0
    reject = "--reject" in argv
    ids = {a for a in argv if not a.startswith("--")}
    papers = db.load_papers(); screened = db.load_json(config.SCREENED, {})
    keep, moved = [], 0
    for c in cands:
        if c["id"] in ids:
            c.pop("candidate", None)
            if not reject:
                c["date_added"] = date.today().isoformat(); papers.append(c)
            for k, v in screened.items():
                if v.get("id") == c["id"]:
                    v["reason"] = "rejected" if reject else "approved"
            moved += 1
        else:
            keep.append(c)
    db.save_json(config.CANDIDATES, keep); db.save_json(config.SCREENED, screened)
    if not reject:
        db.save_papers(papers)
    print(f"{'rejected' if reject else 'approved'} {moved}; {len(keep)} remain in the queue")
    return 0


if __name__ == "__main__":
    sys.exit(main())
