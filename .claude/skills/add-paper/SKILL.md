---
name: add-paper
description: Add a paper to the CANlab publication database (data/papers.json) and open a pull request for Tor to review. Use when a lab member asks to add, list or post a paper, preprint, in-press article, chapter or published version of a preprint on the CANlab site (canlab.science), gives a DOI / bioRxiv / arXiv / PubMed link or a PDF, or asks to attach a PDF, code or data link to an existing paper.
---

# Add a paper to the CANlab site

The site is built from `data/papers.json`. Papers are never pushed straight to `main`: you prepare the change on a
branch and open a pull request; Tor (or whoever he names) reviews and merges, and the site rebuilds by itself.
Read `CLAUDE.md` sections 5 (record schema) and 6 (tags) once before your first paper.

## 1. Gather what the person gave you
- An identifier: DOI, bioRxiv/medRxiv/arXiv link, PubMed id, PMC id. Ask for one if they only gave a title
  (search Crossref/PubMed yourself if you have web access, and confirm the match with them).
- A PDF if they have one (published version preferred; proofs or an accepted manuscript are fine for "in press").
- Status if it is not obvious: published, in press, preprint, under review.
- Code / data / paradigm links (GitHub) if they know them.

The paper must have Tor Wager as an author. Commentaries *about* a lab paper by other people are not records: they
go in that paper's `commentaries` list (ask Tor if unsure).

## 2. Start a branch
```bash
git checkout main && git pull --rebase origin main
git checkout -b add-paper/<short-name>
pip install -r requirements.txt   # once
```

## 3. Add it
```bash
python -m pipeline.add_paper "<identifier>" --pdf <path-or-url> --by "<their name>" \
    [--status "in press"] [--code https://github.com/...] [--data URL] [--paradigm URL] --summary /tmp/add-paper.md
```
The script fetches metadata (OpenAlex, Crossref, PubMed), refuses duplicates, merges a published version into its
preprint record, promotes a paper already waiting in the daily-search queue, saves the PDF into `site/pdf/`, tags
the paper and prints a report. Read the report.

- **No identifier yet** (proofs, chapter, in press without a DOI): write the record as JSON with at least `title`,
  `authors` (`["Surname, I. I.", ...]`), `year`, `journal`, `status`, and optionally `abstract`, `links`, then run
  `python -m pipeline.add_paper --from-json rec.json --pdf ...`. Do not publish proofs that still carry editor
  queries unless Tor says so; add the record without `--pdf` instead.
- **Tagging without an API key** (the usual case on a laptop; the script says "Not tagged"): tag it yourself.
  Read `pipeline/taxonomy.json` and `pipeline/prompts/classify.md`, read the PDF's methods and results (not just the
  abstract), write the JSON the prompt asks for to a file, then run the command again with `--tags-json file.json`
  (after `git checkout data/ site/pdf/` to undo the first attempt), or apply it by editing the record. Follow the
  neuromarker policy in CLAUDE.md section 6: only papers that develop a reusable signature, test one's validity, or
  review signatures get `neuromarker`; using the NPS as an outcome does not count.
- **GitHub repositories found in the PDF** are listed as suggestions. Add only the paper's own repository
  (`--code`), never general toolboxes such as CanlabCore. Check it exists: `git ls-remote https://github.com/o/r`.
- **Brain maps**: if the paper's signature is in canlab/Neuroimaging_Pattern_Masks, add a `maps` link to its folder;
  if it is in the neuromarkers.io gallery, run `python scripts/link_github_repos.py <Pattern_Masks checkout>` or ask
  Tor.

## 4. Check
```bash
python -m pipeline.build_site                 # must finish without errors
git diff --stat                               # only data/papers.json, data/candidates.json and new PDFs
```
Open `site/papers/<id>.html` via `cd site && python -m http.server 8000` if you want to see the page.
Check: title and author list complete (Tor present), year/journal/status right, abstract present, tags sensible,
the summary is one plain sentence.

## 5. Open the pull request
```bash
git add data/papers.json data/candidates.json site/pdf
git commit -m "Add paper: <first author> <year> <short title>"
git push -u origin add-paper/<short-name>
gh pr create --base main --title "Add paper: <first author> <year>" --body-file /tmp/add-paper.md
```
(Without `gh`, open the pull request from the link `git push` prints.) Tell the person the PR link. Do not merge
it yourself unless Tor has said you may.

## Other requests
- Attach a PDF or link to an existing paper: edit its record in `data/papers.json` (`links`, `has_pdf`), copy the
  PDF to `site/pdf/<id>.pdf`, then steps 4-5.
- Fix a tag or typo: edit the record, keep `classification` but add a note, then steps 4-5.
- Several papers: one branch and one PR is fine; run the script once per paper.
