"""Prepare batches of papers for full-text tagging (by an LLM API or a Claude Code subagent).

For each paper: title, citation, abstract, then the first ~14k characters of the full text (when a PDF is available),
plus keyword-in-context snippets for methods terms that decide several tags (deep learning, mediation, mega-analysis...).
Writes work/tagging/batch-NN.md and work/tagging/batch-NN.ids.json.
"""
import json, os, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
papers = json.load(open(ROOT / "data" / "papers.json"))
TEXT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "work" / "pdftext"
OUT = ROOT / "work" / "tagging"; OUT.mkdir(parents=True, exist_ok=True)
BATCH = int(os.environ.get("BATCH", "10"))
HEAD = 14000
TERMS = [r"deep (neural )?network", r"convolutional", r"\bCNN\b", r"transformer", r"large language model", r"\bLLM", r"\bGPT", r"generative (AI|model)", r"foundation model", r"artificial intelligence", r"neural network",
         r"mediat(ion|or)", r"path analysis", r"mega-?analy", r"pooled (data|individual)", r"individual[- ]participant data", r"multi-?study", r"meta-?analy", r"MKDA", r"activation likelihood",
         r"support vector", r"\bSVM\b", r"LASSO", r"principal component regression", r"\bPCR\b", r"partial least squares", r"cross-?valid", r"machine learning", r"decod", r"multivariate pattern", r"representational similarity",
         r"reinforcement learning", r"Bayesian", r"drift diffusion", r"computational model", r"predictive coding", r"simulation",
         r"naloxone", r"remifentanil", r"opioid", r"ketamine", r"cannab", r"pharmacolog",
         r"skin conductance", r"heart rate", r"\bEEG\b", r"\bERP\b", r"\bMEG\b", r"electromyograph", r"pupil",
         r"\bTMS\b", r"tDCS", r"temporal interference", r"deep brain stimulation",
         r"\bPET\b", r"gray matter", r"grey matter", r"voxel-based morphometry", r"cortical thickness", r"diffusion", r"spinal cord", r"\b7\s?T\b",
         r"placebo", r"nocebo", r"expectanc", r"expectation", r"conditioning", r"cue",
         r"reapprais", r"emotion regulation", r"mindfulness", r"empath", r"vicarious", r"compassion", r"social", r"stress", r"cortisol",
         r"craving", r"reward", r"addiction", r"working memory", r"executive", r"attention", r"inhibition",
         r"autonomic", r"interocept", r"inflammat", r"immune", r"brainstem", r"hypothalam", r"vagal", r"cardio",
         r"chronic pain", r"back pain", r"fibromyalgia", r"patients", r"depress", r"anxiety", r"PTSD", r"psychiatr",
         r"signature", r"biomarker", r"neuromarker", r"\bNPS\b", r"SIIPS", r"PINES", r"toolbox", r"software", r"dataset", r"openly available", r"github"]
RX = re.compile("|".join(f"({t})" for t in TERMS), re.I)


def snippets(text, n=60, w=110):
    out = []; last = -1000
    for m in RX.finditer(text):
        if m.start() - last < w:
            continue
        last = m.start()
        out.append("…" + re.sub(r"\s+", " ", text[max(0, m.start() - w): m.end() + w]) + "…")
        if len(out) >= n:
            break
    return out


def text_for(p):
    for l in p.get("links", []):
        if l["type"] == "pdf" and l.get("file"):
            f = TEXT_DIR / (l["file"] + ".txt")
            if f.exists():
                t = f.read_text(errors="ignore")
                if len(t.strip()) > 800:
                    return t
    return ""


todo = [p for p in papers if not p.get("tags") or os.environ.get("ALL")]
print(len(todo), "papers to tag")
for bi in range(0, len(todo), BATCH):
    batch = todo[bi: bi + BATCH]; n = bi // BATCH + 1
    parts = []; ids = []
    for p in batch:
        t = text_for(p)
        mode = "full_text" if t else ("abstract" if p.get("abstract") else "title_only")
        body = ""
        if t:
            t = re.sub(r"[ \t]+", " ", t); t = re.sub(r"\n{2,}", "\n", t)
            head = t[:HEAD]
            snips = snippets(t[HEAD:], n=45)
            body = f"FULL TEXT (first {len(head)} characters):\n{head}\n\nKEYWORD-IN-CONTEXT SNIPPETS FROM THE REST OF THE PAPER:\n" + "\n".join(snips)
        parts.append(f"""==================== PAPER {p['id']} ====================
Citation: {p['citation']}
Title: {p['title']}
Journal: {p.get('journal','')} ({p.get('year')}) · kind: {p.get('kind')} · status: {p.get('status')}
Abstract: {p.get('abstract') or '(none available)'}
Text available: {mode}
{body}
""")
        ids.append({"id": p["id"], "title": p["title"], "mode": mode})
    (OUT / f"batch-{n:02d}.md").write_text("\n".join(parts))
    json.dump(ids, open(OUT / f"batch-{n:02d}.ids.json", "w"), indent=1)
print("batches:", (len(todo) + BATCH - 1) // BATCH, "->", OUT)
