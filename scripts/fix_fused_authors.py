"""Split author entries that the old-site scrape fused together ("Woo, C.-W., Wager, T.D." as one author).

Each fix is explicit so it can be reviewed; authors_short is regenerated for every touched record.
Run once: python scripts/fix_fused_authors.py
"""
import json
import re
from pathlib import Path

PAPERS = Path(__file__).resolve().parents[1] / "data" / "papers.json"

# id -> {fused entry: [replacement entries]}
FIXES = {
    "adams2026emotional": {"Wager, T. D. Vandenbulcke, M.": ["Wager, T. D.", "Vandenbulcke, M."]},
    "chen2026modalityspecific": {"Wald, L. L. Bianciardi, M.": ["Wald, L. L.", "Bianciardi, M."]},
    "kwon2026convergent": {"Botvinik-Nezer, R. Kragel, P. A.": ["Botvinik-Nezer, R.", "Kragel, P. A."]},
    "lee2024representations": {"Lee, S. A., Lee, J.-J.": ["Lee, S. A.", "Lee, J.-J."]},
    "ross2023resolution": {"Koch S.B.J, Olff, M.": ["Koch, S. B. J.", "Olff, M."]},
    "amir2022testretest": {"Mischkowski, D. Necka, E. A.": ["Mischkowski, D.", "Necka, E. A."]},
    "coll2022neural": {"Woo, C.-W., Wager, T.D.": ["Woo, C.-W.", "Wager, T. D."]},
    "eversawm2021letter": {"Evers A.W.M": ["Evers, A. W. M."]},
    "lee2021neuroimaging": {"4, Park, B.": ["Park, B."]},
    "koban2021self": {"Gianaros, P.J. Kober, H.": ["Gianaros, P. J.", "Kober, H."]},
    "ashar2021markers": {"Goldin, P. Gross, J. J.": ["Goldin, P.", "Gross, J. J."]},
    "zhou2021distributed": {"Zhou, F.,, Zhao, W.": ["Zhou, F.", "Zhao, W."]},
    "zheng2020painevoked": {"Hu, B., Wager, T. .D.": ["Hu, B.", "Wager, T. D."]},
    "yu2020toward": {"Zhou, X., Wager, T. D.": ["Zhou, X.", "Wager, T. D."]},
    "geuter2020multiple": {"Geuter, S., Losin, R. E. A.": ["Geuter, S.", "Reynolds Losin, E. A."]},
    "leach2020mouse": {"Leach, S.M., Gibbings, S.L.": ["Leach, S. M.", "Gibbings, S. L."]},
    "zhouf2020empathic": {"Zhou. F, Li, J.": ["Zhou, F.", "Li, J."]},
    "silvestrini2020distinct": {"Chen, J.-I., Piché, M.": ["Chen, J.-I.", "Piché, M."]},
    "evers2020what": {"Bussemaker, J., Colagiuri, B.": ["Bussemaker, J.", "Colagiuri, B."],
                      "Klinger, R., Meeuwis, S. H.": ["Klinger, R.", "Meeuwis, S. H."]},
    "zunhammer2019laterality": {"Bingel, U. on behalf of the Placebo Imaging Consortium": ["Bingel, U."]},
    "xzhu2018exposurebased": {"X. Zhu, B. Suarez-Jimenez, A. Lazarov, L. Helpman, S. Papini, A. Lowell, A. Durosky, M. A. Lindquist, J. C. Markowitz, F. Schneier, T. D. Wager, Y. Neria":
                              ["Zhu, X.", "Suarez-Jimenez, B.", "Lazarov, A.", "Helpman, L.", "Papini, S.", "Lowell, A.", "Durosky, A.", "Lindquist, M. A.", "Markowitz, J. C.", "Schneier, F.", "Wager, T. D.", "Neria, Y."]},
    "kalisch2017resilience": {"Rutten B.P.F": ["Rutten, B. P. F."]},
    "wager2015bayesian": {"Kang. J": ["Kang, J."], "Feldman, Barret, L.": ["Feldman Barrett, L."]},
    "thayer2012metaanalysis": {"Sollers, J. J. I.II, Wager, T. D.": ["Sollers, J. J., III", "Wager, T. D."]},
    # malformed single entries (wrong split, stray punctuation, typos)
    "garavan2022abcd": {"Hagler Jr": ["Hagler, D. J., Jr"], "D.J": []},
    "ashar2021markers": {"Gunning, F.": ["Gunning, F. M."], "M": []},
    "ross2023resolution": {"": []},
    "leroux2024statistical": {"; A2CPS Consortium": ["A2CPS Consortium"]},
    "kelly2024platform": {"… MiSBIE Study Group": ["MiSBIE Study Group"]},
    "wager2005accounting": {"Hernandez, l": ["Hernandez, L."]},
    "chen2026modalityspecific_typo": {"Barret, L. F.": ["Barrett, L. F."]},
    "kalisch2017resilience_vinkers": {"H. Vinkers, C.H.": ["Vinkers, C. H."]},
    "fischbach2024journal": {"Theriault, J. E. Seven Tesla Evidence for Columnar, Rostral–Caudal Organization of the Human Periaqueductal Gray Response in the Absence of Threat: A. Working Memory Study": ["Theriault, J. E."]},
}
# whole author lists replaced (truncated or missing in the scrape; taken from Crossref)
AUTHORS = {
    "lindquist2015groupregularized": ["Lindquist, M. A.", "Krishnan, A.", "López-Solà, M.", "Jepma, M.", "Woo, C.-W.", "Koban, L.", "Roy, M.", "Atlas, L. Y.",
                                      "Schmidt, L.", "Chang, L. J.", "Reynolds Losin, E. A.", "Eisenbarth, H.", "Ashar, Y. K.", "Delk, E.", "Wager, T. D."],
    "anon2017chang": ["Woo, C.-W.", "Chang, L. J.", "Lindquist, M. A.", "Wager, T. D."],
    "reddanmc2019systems": ["Reddan, M. C.", "Wager, T. D."],
}
TRUNCATED = {"evers2018implications", "kelly2024platform"}  # the old site listed these with "…"
TITLES = {
    "anon2017chang": "Building better biomarkers: brain models in translational neuroimaging",
    "fischbach2024journal": "Seven Tesla Evidence for Columnar, Rostral–Caudal Organization of the Human Periaqueductal Gray Response in the Absence of Threat: A Working Memory Study",
}


def short(a):
    """'Surname, I. J.' -> 'Surname IJ' (suffixes like III dropped)."""
    if "," not in a:
        return a.strip()
    sur, rest = a.split(",", 1)
    rest = re.sub(r"\b(Jr|Sr|II|III|IV)\b\.?", "", rest)
    ini = "".join(re.findall(r"[A-ZÀ-Ý]", rest))
    return f"{sur.strip()} {ini}".strip()


def make_citation():
    """make_citation() from normalize_refs.py, loaded without running that script's whole-file pass."""
    src = (Path(__file__).parent / "normalize_refs.py").read_text().split("\nlog = []")[0]
    ns = {"__file__": str(Path(__file__).parent / "normalize_refs.py")}
    exec(compile(src, "normalize_refs.py", "exec"), ns)
    return ns["make_citation"]


def main():
    cite = make_citation()
    papers = json.loads(PAPERS.read_text())
    byid = {p["id"]: p for p in papers}
    for key, fixes in FIXES.items():
        pid = key.split("_")[0]
        p = byid[pid]
        if not any(a in fixes for a in p["authors"]):
            continue  # already fixed (the script is idempotent)
        out, shorts = [], []
        old_short = p.get("authors_short") or []
        for i, a in enumerate(p["authors"]):
            if a in fixes:
                out += fixes[a]
                shorts += [short(x) for x in fixes[a]]
            else:
                out.append(a)
                shorts.append(old_short[i] if i < len(old_short) else short(a))
        p["authors"], p["authors_short"] = out, shorts
        if pid in TITLES:
            p["title"] = TITLES[pid]
        p["citation"] = cite(p)
        print(pid, "->", shorts)
    for pid, auth in AUTHORS.items():
        p = byid[pid]
        if p["authors"] != auth:
            p["authors"], p["authors_short"], p["authors_truncated"] = auth, [short(a) for a in auth], False
            if pid in TITLES:
                p["title"] = TITLES[pid]
            if pid == "anon2017chang":
                p["year"] = p.get("year") or 2017
            p["citation"] = cite(p)
            print(pid, "->", p["authors_short"])
    for pid in TRUNCATED:
        p = byid[pid]
        if not p.get("authors_truncated"):
            p["authors_truncated"] = True
            p["authors"] = ["Atlas, L. Y." if a == "Atlas, Y. A." else a for a in p["authors"]]
            p["authors_short"] = [short(a) for a in p["authors"]]
            p["citation"] = cite(p)
            print(pid, "marked truncated")
    PAPERS.write_text(json.dumps(papers, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
