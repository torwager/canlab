# Adding a paper to canlab.science

Only people with write access to this repository can add papers. Every addition arrives as a pull request, and
nothing appears on the site until Tor (or someone he names) merges it.

## Option 1: the "Add a paper" button (no setup)
1. Open the repository on GitHub → **Actions** → **Add a paper** → **Run workflow**.
2. Paste the DOI, bioRxiv/medRxiv/arXiv link, PubMed id or PMC id. Several at once: separate them with spaces.
3. Optional: a direct link to the PDF, the status (e.g. "in press"), the paper's GitHub repository, a note.
4. Run. In a minute or two a pull request titled "Add paper: …" appears. It lists the metadata, the tags the model
   assigned, the one-sentence summary, and any GitHub repositories cited in the PDF.
5. Tor reviews and merges; the site rebuilds automatically.

It refuses papers without Tor as an author and papers already listed. If the paper is the published version of a
preprint already on the site, it updates that record instead of adding a second one.

## Option 2: Claude Code
Open this repository in Claude Code and ask, for example, "Add this preprint to the lab site: <link>" or "Add the
attached accepted manuscript as in press". Claude follows `.claude/skills/add-paper/SKILL.md`: it runs the same
script, tags the paper from the full text itself when there is no API key, checks the build and opens a pull
request. Use this for anything unusual (no DOI yet, a chapter, a PDF from your computer, fixing an existing record).

## Command line
`python -m pipeline.add_paper <identifier> [--pdf PATH_OR_URL] [--status "in press"] [--code URL] [--tags-json FILE]`
(see the docstring in `pipeline/add_paper.py`).

## One-time repository settings (Tor)
- Add the research assistants as collaborators with **Write** access (Settings → Collaborators).
- Settings → Actions → General → Workflow permissions: tick **Allow GitHub Actions to create and approve pull
  requests** (otherwise the workflow pushes a branch but cannot open the pull request).
- Recommended: Settings → Branches → add a rule for `main` requiring a pull request before merging, so nobody can
  push straight to the live site. (Admins can still merge; the daily bot commits data back to `main`, so either
  allow GitHub Actions to bypass the rule or leave "Do not allow bypassing" unticked.)
