SITE PLAN: how to rebuild the CANlab website, or build a similar lab site for someone else
==========================================================================================
Written by Claude Code for Claude Code, September 2026, after building torwager.github.io/canlab
(repo github.com/torwager/canlab). Read this whole file before starting; then follow the phases in order.
Companion sources worth opening when duplicating: the repo itself (all code), and the sibling project
github.com/torwager/scienceofplacebo from which the design system was inherited.

------------------------------------------------------------------------------------------
0. WHAT THE SITE IS
------------------------------------------------------------------------------------------
A static lab website (no server, no build step for the HTML) hosted on GitHub Pages, with:
- a landing page (banner, rotating picture gallery, tiles with thumbnails, interactive network hero),
- research themes, people, news and press, tools and training, join/participate pages,
- a searchable, tagged publication database (400+ papers) with PDFs, per-paper pages, export to
  reference managers, star lists, a "simple reference list" CV-style view,
- collaborator network (d3 force graph) and bibliometrics pages,
- automation: a daily GitHub Action that searches OpenAlex + PubMed for new lab papers, tags them with an
  LLM, refreshes citation counts and rebuilds; a news/podcast search every two days; a Google Form
  monitor; optional Cloudflare Worker for GitHub sign-in and synced reading lists.
All content lives as JSON in data/ (the single source of truth). pipeline/build_site.py turns it into
site/data/*.json plus one pre-rendered HTML page per paper (SEO). The site's JS renders everything else
client-side. There is intentionally no framework and no bundler.

------------------------------------------------------------------------------------------
1. REPOSITORY LAYOUT (create exactly this)
------------------------------------------------------------------------------------------
README.md, LICENSE (MIT code, CC-BY data), requirements.txt, .gitignore
data/                     source of truth, all JSON
  papers.json             bibliography (schema in section 5)
  people.json             lab members (section 7)
  research.json           {intro, themes:[{id,title,question,paragraphs[],image}]}
  news_posts.json         lab-written posts [{id,title,date,html,text,image,links,source_url,kind,pinned}]
  news.json               auto-collected media items {updated, items:[{title,url,date,source,kind,snippet}]}
  resources.json          books, courses, tools (with thumb), chapters, other
  join.json               openings, general ways to join, participate studies
  candidates.json         daily-search finds awaiting approval;  screened.json  everything already seen
  form_seen.json          Google Form responses already reported
pipeline/                 Python, run with python -m pipeline.<module>
  config.py               site URL, author ids for search, PubMed query, news queries
  build_site.py           data -> site/data + site/papers/<id>.html + feed.xml + sitemap + robots
  taxonomy.json           tag vocabulary (section 6)
  prompts/classify.md     LLM tagging prompt; schemas/llm_output.schema.json structured output
  llm_client.py, classify.py   provider-agnostic tagging (Anthropic or OpenAI), apply() writes tags into a record
  openalex.py, pubmed.py  discovery + enrichment; run_daily.py orchestrates; approve.py promotes candidates
  news.py                 Google News RSS + Apple podcast search (+ optional LLM relevance filter)
  form_monitor.py         polls a published Google Sheet CSV, opens a GitHub issue per new response
  db.py                   ids, dedup helpers
scripts/                  one-off tooling kept for provenance: import_dartmouth.py (scrape of the old site),
                          normalize_refs.py (journal names + APA citations), link_pdfs.py, apply_tags.py,
                          make_tag_bundles.py, reference_changes.py, upload_pdfs.sh
site/                     the published site (GitHub Pages serves this folder via the workflow)
  index.html research.html people.html publications.html paper.html (template) news.html resources.html
  join.html network.html bibliometrics.html mylist.html account.html about.html
  assets/app.css app.js layout.js config.js hero.js account.js hero-graph.json
  assets/img/ (photos, thumbnails, covers)  assets/gallery/ (gallery frames + frames.json)
  assets/source/ (original logo and figure files)  assets/favicon.svg favicon-32.png apple-touch-icon.png icon-192.png og.jpg
  pdf/<id>.pdf and pdf/author_manuscripts/<id>.pdf   (committed to git, ~900 MB; see section 9)
  data/ and papers/       generated, gitignored
worker/                   Cloudflare Worker (GitHub OAuth, KV lists) + README; optional
.github/workflows/        daily.yml (search + build + deploy, also on push), news.yml, form.yml
work/                     gitignored scratch (scraped HTML, PDF text, tagging batches)

------------------------------------------------------------------------------------------
2. DESIGN SYSTEM (copy app.css from the repo; these are the rules behind it)
------------------------------------------------------------------------------------------
Inherited from scienceofplacebo.org so the two sites read as a family.
- Palette (CSS variables in :root, with dark-mode overrides under prefers-color-scheme and [data-theme]):
  warm paper --bg #faf8f4, --bg-2 #f2efe8, --bg-3 #e9edf0; ink #1a2332; muted #646b75; lines #e3dfd6;
  accent amber #e9b949 (deep #c7931a, soft #fbf0d0) reserved for interaction/energy; steel blue #6f8fb0
  (deep #3f6390, soft #e3ebf3) as the secondary. Never introduce other hues except inside pictures.
- Type: Fraunces (variable serif) for h1/h2/h3 and paper titles, Inter for body, JetBrains Mono for dates
  and DOIs; Google Fonts link in every page head. Headings weight 400, tight letter-spacing.
- Components: pill buttons (.btn, .btn.primary amber), chips (.chip, coloured per tag axis), cards
  (.card, .paper, .res-card, .tile with the animated conic "glow" border on hover), fixed blurred header
  (.site-header), footer with three columns, scroll-reveal (.rv/.rv.in with IntersectionObserver),
  sticky filter sidebar (.filters), sticky "On this page" side navigation (.with-sidenav/.sidenav).
- Radii 18px cards / 10px small; soft shadows; max content width 1180px; responsive breakpoints at
  ~860-960px (two columns -> one), 640px (tiles), 560px (news).
- Every page: same <head> block (meta description, OG tags pointing at assets/og.jpg 1200x630, canonical,
  favicon links WITH a ?v= cache-buster, fonts, app.css?v=), <div id="site-header"></div> and
  <div id="site-footer"></div> filled by layout.js, scripts config.js, app.js, layout.js (+account.js,
  hero.js, d3/minisearch from cdnjs where needed) also with ?v= versions. Bump the version whenever
  app.js/app.css/layout.js change or users get stale caches (this bit us twice).
- Navigation (layout.js): Research · People · Publications · News · Tools & training · Explore ▾
  (Collaborator network, Bibliometrics, Science of Placebo, Elements of fMRI tutorials, PBS shared
  resources, fMRI course) · Join ▾ (Join our team, Participate in research). "My list", "Sign in",
  "About this site" live only in the footer. No Discussion board (removed on request).
- Brand mark: the brain outline cropped from the lab logo, bold-stroked, in a 34px amber tile beside
  "CANlab" (b for CAN). Favicon = brain slice + three connected coloured nodes (orange, green, purple)
  echoing the logo. og.jpg = full logo on paper with a caption line. Generate all with PIL at 4-8x
  and downsample (see the python in git history / section 12 recipes).

------------------------------------------------------------------------------------------
3. LANDING PAGE (index.html)
------------------------------------------------------------------------------------------
Order of sections:
1. Sticky "curtain" (100vh): a single full-width h1 banner "Cognitive and Affective Neuroscience Lab"
   (nowrap on desktop), the lab's one-paragraph description verbatim from the old site, then a
   full-width GALLERY that auto-rotates every 6 s with arrows and dots. Gallery frames are ROWS of
   2-4 pictures that stretch edge to edge: each <img> gets flex: <aspect> 1 0, height 100%,
   object-fit cover, so a row's pictures fill the width with mild cropping. Frame definitions are in
   assets/gallery/frames.json [[{src, ar}, ...], ...]. Pictures were extracted individually from the
   lab's PowerPoint (python-pptx, apply the shape rotation stored in the pptx, drop tiny thumbnails),
   plus figures the PI supplied; first row ends with the colour logo on white; no people-photos are
   required but lab photos are welcome. Keep 15-20 rows.
   No buttons under the blurb, no "move your cursor" hint (let people discover the hero).
2. Fact strip: publications, since year, lab members past and present (NO citation counts, NO PDF count).
3. "Explore the lab": grid with a single column of wide, short TILES on the left (icon = 64px square
   THUMBNAIL cropped from a brain/data picture, title, one-line blurb, arrow; no people in thumbnails)
   and the interactive network HERO sticky on the right. Tiles: Research, Publications, People,
   Tools & training, News, Collaborator network, Join us, Reading lists.
4. "Recent papers" (three most recent cards), "In the news" (three latest items), a dark strip about
   open science (links to CanlabCore, Neuroimaging_Pattern_Masks, scienceofplacebo.org), and an
   "About the lab" block with the lab photo. Footer.

THE HERO (assets/hero.js + hero-graph.json). Rules the PI converged on after several rounds:
- Graph extracted from the PI's network drawing (TIFF): nodes by saturated-blob detection, edges by
  testing straight segments for line pixels; 49 nodes / 150 edges stored as JSON in image pixels.
- All nodes light grey (#d9d5cc fill, #c3bfb5 rim; dark theme #3a414d/#4a5261), thin grey edges,
  transparent background, subtle ±3% breathing only; respects prefers-reduced-motion.
- Firing: pointer near a node lights it yellow (#ffd84a); each of its edges lights up progressively from
  the node outward (the EDGE itself changes colour, no travelling dots, no glow/shadowBlur: those made it
  slow) shading yellow -> orange (#ff8a2a) with travel; arriving node turns orange and fades in 700 ms.
- Propagation probabilities per edge: hop1 0.7, hop2 0.5, hop3 0.2, hop4 0.2, nothing beyond hop 4;
  max 120 pulses in flight; 600 ms refire lockout per node. (Unlimited depth "cycled forever".)
- Spontaneous activity: a random node fires every 7-14 s while on screen (2.5-6 s was "too much").
- Click/tap fires the nearest node. Exposes window.CANLAB_HERO.fire(). Fetches the graph JSON relative
  to the script's own src so it works from subpages. Uses rAF only while visible and animating.
- Same hero is reused on Research and Publications page headers: a .head-hero grid, text/tags on the
  left half, canvas (aspect 1/1, max 480-520px) on the right.

------------------------------------------------------------------------------------------
4. OTHER PAGES
------------------------------------------------------------------------------------------
Research: intro paragraph, theme chips (jump links), hero on the right, then one .theme section per
  theme alternating text/figure sides, each with the guiding question in italics, paragraphs, the figure,
  and a "Related publications" link into the database with matching tags. Sticky side nav of themes.
People: PI card (photo, title, bio, links: CV, Google Scholar, GitHub, department page, Publications
  filter), then sections in this order: Postdocs, Graduate Students, Staff, Undergraduate Research
  Assistants, Visiting Scholars, Former Postdocs and Graduate Students, Former Visiting Faculty and
  Scholars, Former Staff, Former Undergraduate RAs. Cards = square photo + name + role; click expands
  to the bio inline (the card spans the row). Section chips at top AND a sticky side nav. No email
  links. Google Scholar link per person when a verified profile exists.
Publications: header (left) + hero (right); three "book tiles" (Elements of fMRI with cover + MIT
  Press link, Elements tutorials, Principles of fMRI with cover); counts row (publications, years,
  last updated; no citations, no PDF count); "Other ways to view" links (Scholar, Bibliometrics,
  Network); search box (MiniSearch over title+abstract+keywords+authors+journal, prefix+fuzzy) and
  author box (surname or "Surname II"); left sidebar of tag chips grouped by axis with counts (any
  within an axis, AND across axes); sort (year, relevance, most cited, oldest), year range, Export ▾
  (BibTeX, RIS, DOI list, CSV, formatted citations), "my list" and "with PDF" toggles, and a
  "Simple reference list" toggle (CV-style: books first, then years descending, title linked to PDF,
  [PDF] [link] [Brain maps] etc. after each). Cards show: star, title (links to the paper page),
  authors (et al. when truncated), year, journal/vol/pages, status badges (preprint, in press,
  chapter), summary sentence, tag chips (clickable to filter), link pills (PDF amber, Brain maps steel,
  Publisher, PubMed, Details), and a "commentary" bubble for editorials written about the paper.
  Year headings with counts and a year-jump bar. Above the search: a collapsible "N new papers found
  by the daily search, awaiting review" block when candidates.json is non-empty.
Paper pages (site/papers/<id>.html, generated from paper.html): full head meta + JSON-LD
  ScholarlyArticle, static fallback content, then JS renders: journal line, title, all authors, link
  pills, star, "In one sentence" callout (summary + key finding), abstract, tag rows (clickable),
  free keywords, citation/DOI/PMID/citation count, note when the PDF is an author manuscript, how it
  was tagged with a "suggest a correction" issue link, related papers (tag overlap), commentary bubbles.
News: two columns. Left: tabs All / Lab posts / In the media, feed of posts (full HTML, image thumb)
  and auto-collected media items (title, source, date, snippet). Right (sticky): "Pinned" pane
  (posts with pinned:true, kept out of the feed) and "New papers" pane (data/newpapers.json built on
  every run: papers with date_added within 180 days + candidates marked "new").
Tools & training: Books (covers, MIT Press, tutorials), Courses (Coursera x2, MIND course at
  torwager.github.io/mindfmricourse), Open-source tools (10 cards, each with a brain THUMBNAIL and link
  to GitHub), fMRI methods chapters (PDF links), Elsewhere (open-tools papers filter, Science of
  Placebo). Sticky side nav.
Join: sections Open positions (cards with poster image), Other ways to join, Participate in research
  (study cards with screening link, email, compensation). Side nav; nav dropdown targets #team and
  #participate.
Network: d3 force graph built in the browser from index.json; nodes = authors with >=3 papers (cap 400);
  the PI's edges hidden by default (toggle) because they form a star; co-authorship vs similarity
  (cosine over tag profiles) modes; keyword menu; find box; side panel with tags, recent papers, link
  to the author's papers; node colour = current member (amber) / alumnus (steel) / other (grey) using
  people.json; "More to explore" tiles at the bottom.
Bibliometrics: publications per year, topics by year, approaches by year (stacked, clickable), three
  tag-count panels, top co-authors (PI excluded), most-cited table (the ONLY place citation counts
  appear; OpenAlex/Crossref counts are otherwise hidden because Google Scholar counts cannot be pulled).
My list / Sign in: star lists in localStorage, named lists, import/export, export menu; account.js
  syncs through the worker when configured. About: how the site is built, tags, privacy, contributing.

------------------------------------------------------------------------------------------
5. PAPER RECORD SCHEMA (data/papers.json is a list of these)
------------------------------------------------------------------------------------------
id (stable slug: firstauthor+year+firstlongword, e.g. wager2013fmribased), title, authors ["Surname, I. I."],
authors_short ["Surname II"] (used for author search/network; variants merged at build via
AUTHOR_ALIASES + prefix rule), authors_truncated (bool), year, date, status (published|in press|preprint|
under review), kind (article|chapter|preprint|proceedings|other), journal (book title for chapters),
volume, issue, pages, doi, pmid, pmcid, openalex_id, abstract, abstract_source, cited_by_count,
oa_url, landing_url, keywords, links [{type: pdf|publisher|maps|code|data|paradigm|video|supplement|
preprint, label, url, url_original, version: publisher|author_manuscript}], has_pdf, citation
(regenerated APA-style string), citation_original, commentaries [{title, authors, journal, year, doi,
pdf, note}], preprint_doi, tags {topic:[], approach:[], type:[one]}, summary, key_finding,
free_keywords, classification {model, input_mode, confidence, notes, classified_at}, date_added, source.
Rule: only papers with the PI as an author are records; editorials/commentaries ABOUT a paper by others
are attached to that paper as commentaries. A preprint and its published version are one record with a
preprint link.

------------------------------------------------------------------------------------------
6. TAG TAXONOMY (pipeline/taxonomy.json) AND TAGGING
------------------------------------------------------------------------------------------
Three axes, one colour each (violet topic, steel approach, slate type):
topic (multi): placebo, pain, chronic_pain, emotion, emotion_regulation, empathy, stress,
  expectation_learning, social, reward_craving, cognitive_control, brain_body, clinical, perception.
approach (multi): fmri, neuroimaging_methods, neuromarker, machine_learning, ai_integration,
  computational_model, mediation, meta_analysis, mega_analysis, genetics, pharmacology,
  psychophysiology, brain_stimulation, other_imaging, behavioral, open_tools.
type (single): empirical, review, methods, chapter, commentary.
Each value has a definition the model reads. Tagging must be done from FULL TEXT when a PDF exists
(features like deep-learning analysis or mediation are often absent from abstracts), else abstract,
else title; store input_mode and confidence and show them on the paper page.
How the first pass was done without an API key: scripts/make_tag_bundles.py packs ~12 papers per
batch (citation, abstract, first 14k chars of PDF text + keyword-in-context snippets from the rest),
one Claude Code subagent (sonnet) per batch reads taxonomy.json + prompts/classify.md and writes
batch-NN.tags.json; scripts/apply_tags.py validates ids against the taxonomy and writes them in.
36 batches for 400 papers; re-tag low-confidence ones once their PDFs are found. With an API key the
daily pipeline tags candidates automatically (classify.py, structured JSON output).
Automatic rule at build: any paper with a maps/code/data/paradigm link gets approach open_tools.
Genetics was added after the first pass and back-filled by keyword; expect to add values later too.

------------------------------------------------------------------------------------------
7. PEOPLE, PHOTOS, GOOGLE SCHOLAR
------------------------------------------------------------------------------------------
people.json entries: id (slug), name, role, section, current (bool), img (file in assets/img), bio
(paragraphs), links [{label,url}] (Google Scholar, CV, GitHub, lab/department pages; NO email), title
(PI only), source_url. Photos: scrape from the old site (full-size, not the -300x200 thumbnails), fix
EXIF orientation, cap ~800-1000 px, JPEG q80-85; convert large PNG photos to JPEG.
Google Scholar has no API and blocks automated search pages; what worked: WebSearch for
"<name> Google Scholar <field>" and accept a profile ONLY when name + affiliation/topics match; the PI
supplies their own profile id. Roughly half of postdocs/students had profiles; undergrads rarely.
Section decisions the PI wanted: split "Former Staff" (full-time RAs, lab managers) from "Former
Undergraduate RAs"; keep alumni sections; a visiting-faculty alumna who was a postdoc goes under
Former Postdocs. Check photos actually show the named person (one was mislabelled on the old site).

------------------------------------------------------------------------------------------
8. BUILDING THE BIBLIOGRAPHY FROM AN OLD SITE OR CV (the hard part)
------------------------------------------------------------------------------------------
1. Scrape the old publications page keeping the HTML: split paragraphs on <br> runs but only start a
   new citation where the fragment begins with an author list; journal = first <em>/<i> after the year
   that is not "et al."; capture every link with its label and classify by label/host (pdf, publisher,
   maps for github.com/canlab/Neuroimaging_Pattern_Masks, paradigm, code, data, video, supplement).
   Book chapters: split "Title. In: Book (Eds.)" into title + book, kind=chapter. Dedupe by normalized
   title (the old page listed several papers twice), merging links.
2. Enrich by title: OpenAlex works?search=<title> is best but rate-limits anonymous use hard (HTTP 429
   after ~150 calls) unless you pass mailto/api_key; Crossref query.bibliographic + PubMed E-utilities
   (esearch by DOI[AID], efetch for abstracts/PMCID) worked as the fallback with ~1 s pacing. Always
   VALIDATE a match by title similarity (>=0.85 on normalized titles) and first-author surname; when a
   DOI was extracted from a PDF's text, verify it against Crossref's title or you will attach a cited
   reference's DOI (this happened for two chapters). bioRxiv DOIs go to preprint_doi, not doi.
3. Compare with the PI's CV: parse the numbered publication list (restrict to the publications section;
   other sections are numbered too), fuzzy-match titles, review the unmatched by first author + year,
   add the genuinely missing ones (10 here) and fix years/venues where the CV is more current.
4. Normalize journal names (NeuroImage, Pain, The Journal of Pain, The Lancet Psychiatry ...) and
   regenerate every citation in one style: Authors (Year). Title. Journal, Vol(Issue), Pages. DOI.
   Chapters: "In Book (Editors, Eds.), Publisher, pp." Keep citation_original. Write an
   updated_references.txt log of every change (scripts/reference_changes.py, diff against the git
   baseline of the original import).
5. Link the canlab Neuroimaging_Pattern_Masks repo: fetch its tree (gh api .../git/trees/master
   ?recursive=1), match "YYYY_Author_..." folders to papers by year + author, review by hand, add
   links of type maps. The NPS itself is not in the public repo.

------------------------------------------------------------------------------------------
9. PDFs
------------------------------------------------------------------------------------------
The PI wants PDFs in the repo: site/pdf/<id>.pdf (publisher version) and site/pdf/author_manuscripts/
<id>.pdf (PubMed/HHS author manuscripts, labelled as such on the site). ~900 MB is fine for git and
Pages but a single push of that size fails over HTTPS: commit the PDFs in ~170 MB chunks and push each
commit separately; set http.version HTTP/1.1 and a large http.postBuffer (LibreSSL "bad record mac"
errors otherwise). Keep the old files also as assets of a GitHub release as a backup.
Sources, in order: the old site's PDFs; the PI's Dropbox archive of published PDFs (index every PDF's
first-page text with PyMuPDF, match by year folder + title words, then VERIFY with a strict sliding-
window title similarity >= 0.72 on the first pages, because word-overlap alone picked wrong papers;
prefer files whose first page has journal/DOI markers and penalise drafts, supplements, cover letters);
the PI's Paperpile/Google Drive folder; Unpaywall best_oa_location; publisher citation_pdf_url;
Europe PMC/PMC (mark author manuscripts). Paywalled publishers (Wiley, Elsevier, LWW/Pain, SAGE,
Springer, OUP, Cambridge, IEEE) need the PI's institutional login: list them with direct PDF URLs and
let the PI download them; never try to defeat CAPTCHAs. Detect author manuscripts by "HHS Public Access"
/ "Author manuscript" on page 1. Scanned PDFs have no text layer: keep them, skip verification.

------------------------------------------------------------------------------------------
10. AUTOMATION
------------------------------------------------------------------------------------------
daily.yml (cron + workflow_dispatch + push): pip install, python -m pipeline.run_daily --days 14
--refresh-citations 60 (OpenAlex author_works by the PI's OpenAlex author id A5040523395 + PubMed
author/affiliation query; new items must list the PI as author; tagged with the LLM if a key exists;
written to candidates.json and screened.json; never auto-added to papers.json), commit data back,
build_site, upload-pages-artifact, deploy-pages. Opens/updates an issue labelled pipeline-failure on
failure. The bot commits mean you must `git pull --rebase` before every push.
news.yml every 2 days: Google News RSS for the PI's name/lab/topics + Apple podcast search, optional
LLM relevance filter, keeps 180 days. form.yml every 30 min: reads the form's response sheet published
as CSV (secret FORM_CSV_URL) and opens a GitHub issue per new row (the only way without Google API
credentials; the in-app browser cannot open docs.google.com).
Secrets/vars to set: ANTHROPIC_API_KEY or OPENAI_API_KEY, optionally OPENALEX_API_KEY, NCBI_API_KEY,
CANLAB_CONTACT_EMAIL, FORM_CSV_URL. Analytics: Cloudflare Web Analytics token in config.js
(cookie-free); leave empty until the owner creates it. Sign-in: worker/README.md (GitHub OAuth app +
Cloudflare KV + wrangler deploy, then communityApi in config.js).

------------------------------------------------------------------------------------------
11. DEPLOYMENT AND DOMAINS
------------------------------------------------------------------------------------------
Repo must be public for free Pages and public release assets. Enable Pages with build_type=workflow
(gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow) BEFORE the first push so the
workflow's deploy step works. Verify after each deploy with curl on stats.json and a few pages, using
?v=<timestamp> to dodge the CDN cache. Custom domain: A records to GitHub's four IPs + www CNAME, then
add a CNAME file and enforce HTTPS; a second domain must redirect at the registrar; an old WordPress
site redirects via its settings/plugin.

------------------------------------------------------------------------------------------
12. RECIPES AND GOTCHAS (things that cost time)
------------------------------------------------------------------------------------------
- Working directory drifts between Bash calls in this harness (cd persists): use absolute paths.
- The in-app browser pane is often hidden: layout measurements return 0 and screenshots of scrolled
  positions come back blank. Use resize_window 1280x900 before measuring, verify via DOM queries
  (clientWidth, querySelectorAll counts) and, to see a lower section, remove the sections above it with
  JS and screenshot at scrollTop 0. Local python http.server + browser cache serves stale JS/CSS: reload
  with ?v= on the page URL or bump asset versions.
- A stray extra </div> silently pushed the hero out of its grid: validate tag balance with a small
  HTMLParser check after editing markup with string replacement.
- Monitor/until loops that grep for their own command text never finish; watch a PID or an output file.
- Subagents (general-purpose, sonnet for tagging) are the way to parallelise: tagging batches, people
  research, PDF downloads, page builds. Give them exact file paths, the design tokens, a verification
  step, and forbid git. Cap concurrency at 20.
- Image handling: PIL only (no ImageMagick/cairosvg); render icons at 4-8x and LANCZOS down; make
  near-white pixels transparent in logos that carry a white box; pptx pictures may need the shape's
  rotation applied; convert big PNG photos to JPEG; keep the repo's image folder under ~30 MB.
- Author-name variants (Barrett LF / Feldman Barrett L, Lindquist M / MA) must be merged or the network
  and co-author counts split people; keep an alias map in build_site.py.
- Do not send the user's email to third-party APIs unless they ask; use polite pacing instead.
- Keep every user decision in this file when they refine something (hero probabilities, what not to show,
  section orders): the same points came up repeatedly.

------------------------------------------------------------------------------------------
13. CHECKLIST TO DUPLICATE FOR ANOTHER LAB
------------------------------------------------------------------------------------------
[ ] Create repo (public), enable Pages (workflow), clone this repo's site/assets/app.css, app.js,
    layout.js, config.js, hero.js, pipeline/, scripts/, workflows, README as the starting point.
[ ] Replace identity: names, URLs (config.py SITE_URL, config.js siteUrl/repo, canonical/OG tags in
    every page head, footer text), logo (assets/source), og.jpg, favicons, brand mark.
[ ] Collect content: lab description, research themes + figures, people + photos + roles + sections,
    news posts, tools/courses/books, openings/studies. Fill data/*.json.
[ ] Bibliography: scrape old site and/or parse CV -> papers.json; enrich (Crossref/PubMed/OpenAlex);
    validate DOIs; normalize citations; find PDFs; link pattern-mask/code/data repos.
[ ] Tag every paper from full text (subagent batches or API); review low-confidence ones.
[ ] Landing page: gallery frames from the lab's pictures; hero graph (extract from a drawing or reuse
    hero-graph.json); tile thumbnails from brain/data pictures.
[ ] Set author ids/queries for the daily search; set secrets; run build_site; preview locally
    (python -m http.server in site/); check every page and console; commit in chunks; push; verify live.
[ ] Hand the owner: paywalled PDFs to download, form-monitor setup step, analytics token, worker deploy,
    custom-domain DNS steps, Scholar ids that could not be found.
