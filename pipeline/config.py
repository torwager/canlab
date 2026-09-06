import os
from pathlib import Path

# local runs: pick up secrets from a gitignored .env (KEY=value lines); CI uses repository secrets
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PAPERS = DATA / "papers.json"            # the bibliography (curated; every record is shown)
CANDIDATES = DATA / "candidates.json"    # daily-search finds awaiting approval (auto-tagged, shown in a queue)
SCREENED = DATA / "screened.json"        # everything the daily search has already looked at
SITE = ROOT / "site"
SITE_DATA = SITE / "data"

SITE_URL = os.environ.get("CANLAB_SITE_URL", "https://torwager.github.io/canlab")
CONTACT_EMAIL = os.environ.get("CANLAB_CONTACT_EMAIL", "")
TOOL_NAME = "canlab-site"
NCBI_API_KEY = os.environ.get("NCBI_API_KEY")
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY")

# Whose papers to look for. OpenAlex author IDs are the most reliable handle; PubMed uses an author + affiliation query.
OPENALEX_AUTHOR_IDS = [a for a in os.environ.get("CANLAB_OPENALEX_AUTHORS", "A5040523395").split(",") if a]  # Tor D. Wager
PUBMED_QUERY = '(Wager TD[Author] OR Wager T[Author]) AND (Dartmouth[Affiliation] OR Colorado[Affiliation] OR Columbia[Affiliation] OR pain[tiab] OR placebo[tiab] OR fMRI[tiab] OR brain[tiab] OR neuro*[tiab] OR emotion[tiab])'
LAB_AUTHOR_SURNAMES = {"wager"}

# News: Google News RSS queries about the lab and its work
NEWS_QUERIES = ['"Tor Wager"', '"Wager" Dartmouth pain brain', '"Cognitive and Affective Neuroscience" Dartmouth', '"neurologic pain signature"', '"pain reprocessing therapy" Wager']
FEED_CAP = 24
