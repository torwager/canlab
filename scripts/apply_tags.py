"""Apply tagging results to data/papers.json.

Input files: work/tagging/batch-NN.tags.json, each a JSON array of objects
  {"id": ..., "tags": {"topic": [...], "approach": [...], "type": "..."}, "summary": ..., "key_finding": ..., "free_keywords": [...], "confidence": 0.9, "notes": ...}
Usage: python scripts/apply_tags.py [--model "claude-sonnet-5 (Claude Code)"] [files...]
"""
import glob, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline import classify  # noqa: E402
from pipeline.llm_client import load_taxonomy  # noqa: E402

args = sys.argv[1:]
model = "claude-sonnet-5 (Claude Code subagent)"
if "--model" in args:
    i = args.index("--model"); model = args[i + 1]; del args[i:i + 2]
files = args or sorted(glob.glob(str(ROOT / "work" / "tagging" / "batch-*.tags.json")))
papers = json.load(open(ROOT / "data" / "papers.json"))
by_id = {p["id"]: p for p in papers}
tax = load_taxonomy()
valid = {ax["id"]: {v["id"] for v in ax["values"]} for ax in tax["axes"]}
modes = {}
for f in glob.glob(str(ROOT / "work" / "tagging" / "batch-*.ids.json")):
    for x in json.load(open(f)):
        modes[x["id"]] = x["mode"]
n = 0; bad = []
for f in files:
    for d in json.load(open(f)):
        p = by_id.get(d.get("id"))
        if not p:
            bad.append((f, d.get("id"), "unknown id")); continue
        t = d.get("tags") or {}
        for ax in ("topic", "approach"):
            t[ax] = [v for v in (t.get(ax) or []) if v in valid[ax]]
        if t.get("type") not in valid["type"]:
            t["type"] = "empirical" if p.get("kind") != "chapter" else "chapter"
        d["tags"] = t
        classify.apply(p, d, model, modes.get(p["id"], "abstract"))
        # genetics was added to the vocabulary after the first tagging pass: assign it from strong keyword evidence
        blob = " ".join([p.get("title", ""), p.get("abstract", "")[:3000], " ".join(p.get("free_keywords") or []), d.get("notes") or ""])
        if re.search(r"\b(genetic|genome|gwas|heritab|twin study|twins\b|polygenic|gene expression|transcriptom|snp\b|enigma)", blob, re.I) and "genetics" not in p["tags"]["approach"]:
            p["tags"]["approach"].append("genetics")
        n += 1
json.dump(papers, open(ROOT / "data" / "papers.json", "w"), indent=1, ensure_ascii=False)
print(f"applied {n} tag sets; {len(bad)} problems", bad[:10])
print("tagged:", sum(1 for p in papers if p.get("tags")), "of", len(papers))
