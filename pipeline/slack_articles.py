"""Journal club: import papers shared in the lab's Slack #articles channel into data/journal_club.json.

What it does (idempotent; re-run daily):
  1. Reads new messages from the channel (SLACK_BOT_TOKEN, scopes channels:history channels:read users:read
     reactions:read; the bot must be a member of the channel; private channels need groups:* instead).
  2. Finds paper links in each message (DOI, publisher, PubMed, bioRxiv, Nature, ...), resolves the paper's
     metadata (Crossref by DOI, PubMed by DOI/title, Unpaywall for an open-access PDF), and keeps Slack's own
     unfurl title/text as a fallback when no DOI can be found.
  3. Saves the thread replies and reactions as the paper's discussion, attributed by Slack display name
     (users listed in JOURNAL_CLUB_ANON are shown as "lab member").
  4. Tags each paper with the site's taxonomy using the LLM (pipeline.classify) from title + abstract.

Environment: SLACK_BOT_TOKEN (required), SLACK_ARTICLES_CHANNEL (name or id, default "articles"),
JOURNAL_CLUB_ANON (comma-separated Slack user ids to anonymise), plus the LLM key used elsewhere.
Usage: python -m pipeline.slack_articles [--full] [--no-llm] [--limit N]
"""
import argparse, json, os, re, sys, time, urllib.parse
import requests
from . import config
from .db import make_id

OUT = config.DATA / "journal_club.json"
API = "https://slack.com/api/"
UA = {"User-Agent": "canlab-site journal club/1.0"}
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>|)\]}]+", re.I)
SKIP_HOSTS = ("slack.com", "slack-files.com", "twitter.com", "x.com", "bsky.app", "youtube.com", "youtu.be", "google.com/search", "giphy.com")


def slack(method, token, **params):
    for attempt in range(5):
        r = requests.get(API + method, headers={"Authorization": f"Bearer {token}", **UA}, params=params, timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5"))); continue
        j = r.json()
        if not j.get("ok"):
            raise RuntimeError(f"Slack {method}: {j.get('error')}")
        return j
    raise RuntimeError(f"Slack {method}: rate limited")


def find_channel(token, name):
    if name.startswith("C") and name.upper() == name:
        return name
    # private channels need the groups:read scope; fall back to public channels only when it is missing
    for types in ("public_channel,private_channel", "public_channel"):
        cursor = None
        try:
            while True:
                j = slack("conversations.list", token, types=types, limit=1000, exclude_archived="true", **({"cursor": cursor} if cursor else {}))
                for c in j["channels"]:
                    if c["name"] == name.lstrip("#"):
                        return c["id"]
                cursor = (j.get("response_metadata") or {}).get("next_cursor")
                if not cursor:
                    break
        except RuntimeError as e:
            if "missing_scope" in str(e) and "private" in types:
                continue
            raise
        break
    raise SystemExit(f"channel #{name} not found: the app must be added to the channel (channel details > Integrations > Add apps), and a private channel needs the groups:read/groups:history scopes")


_users = {}
def user_name(token, uid, anon):
    if not uid:
        return "lab member"
    if uid in anon:
        return "lab member"
    if uid not in _users:
        try:
            u = slack("users.info", token, user=uid)["user"]
            _users[uid] = u.get("profile", {}).get("display_name") or u.get("real_name") or u.get("name") or "lab member"
        except Exception:
            _users[uid] = "lab member"
    return _users[uid]


def clean_text(t):
    t = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2 (\1)", t or "")
    t = re.sub(r"<(https?://[^>]+)>", r"\1", t)
    t = re.sub(r"<@[A-Z0-9]+>", "@member", t)
    t = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", t)
    return t.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").strip()


def links_in(msg):
    urls = re.findall(r"<(https?://[^|>]+)", msg.get("text") or "")
    for a in msg.get("attachments") or []:
        for k in ("original_url", "from_url", "title_link"):
            if a.get(k):
                urls.append(a[k])
    for b in msg.get("blocks") or []:
        for el in b.get("elements", []):
            for e in el.get("elements", []):
                if e.get("type") == "link" and e.get("url"):
                    urls.append(e["url"])
    out = []
    for u in urls:
        u = u.split("?utm")[0].strip()
        if any(h in u for h in SKIP_HOSTS) or u in out:
            continue
        out.append(u)
    return out


def doi_from(url, text=""):
    for s in (url, text):
        m = DOI_RE.search(urllib.parse.unquote(s or ""))
        if m:
            return m.group(0).rstrip(".,;)").lower()
    return None


def crossref(doi):
    try:
        r = requests.get("https://api.crossref.org/works/" + urllib.parse.quote(doi), headers=UA, timeout=40)
        if r.status_code != 200:
            return None
        w = r.json()["message"]
        au = [f"{a.get('family','')}, {' '.join(x[0] + '.' for x in a.get('given','').split())}".strip(", ") for a in w.get("author", []) if a.get("family")]
        dp = (w.get("issued") or w.get("created") or {}).get("date-parts", [[None]])[0]
        return {"title": (w.get("title") or [""])[0], "authors": au, "journal": (w.get("container-title") or [""])[0], "year": dp[0] if dp else None,
                "abstract": re.sub(r"<[^>]+>", " ", w.get("abstract") or "").strip() or None, "doi": doi, "type": w.get("type")}
    except Exception:
        return None


def pubmed_by_doi(doi):
    try:
        r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params={"db": "pubmed", "term": f"{doi}[AID]", "retmode": "json"}, headers=UA, timeout=40).json()
        ids = r["esearchresult"]["idlist"]
        if not ids:
            return None
        x = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi", params={"db": "pubmed", "id": ids[0], "retmode": "xml"}, headers=UA, timeout=40).text
        ab = " ".join(re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", x, re.S))
        pmc = re.search(r'<ArticleId IdType="pmc">(PMC\d+)</ArticleId>', x)
        return {"pmid": ids[0], "abstract": re.sub(r"<[^>]+>", "", ab).strip() or None, "pmcid": pmc.group(1) if pmc else None}
    except Exception:
        return None


def unpaywall(doi):
    email = config.CONTACT_EMAIL or "journalclub@example.org"
    try:
        r = requests.get(f"https://api.unpaywall.org/v2/{doi}", params={"email": email}, headers=UA, timeout=40)
        if r.status_code != 200:
            return None
        loc = r.json().get("best_oa_location") or {}
        return loc.get("url_for_pdf") or loc.get("url")
    except Exception:
        return None


def page_meta(url):
    """Title/description from a landing page's meta tags, for links without a DOI."""
    try:
        r = requests.get(url, headers={**UA, "User-Agent": "Mozilla/5.0"}, timeout=30)
        h = r.text[:200000]
        g = lambda p: (re.search(p, h, re.I | re.S) or [None, None])[1]
        return {"title": g(r'<meta[^>]+property="og:title"[^>]+content="([^"]+)"') or g(r"<title>(.*?)</title>"),
                "abstract": g(r'<meta[^>]+(?:name|property)="(?:description|og:description)"[^>]+content="([^"]+)"'),
                "doi": g(r'<meta[^>]+name="citation_doi"[^>]+content="([^"]+)"'), "pdf": g(r'<meta[^>]+name="citation_pdf_url"[^>]+content="([^"]+)"')}
    except Exception:
        return {}


def resolve(url, unfurl):
    doi = doi_from(url) or doi_from(unfurl.get("title_link") or "")
    meta = {}
    if not doi:
        meta = page_meta(url)
        doi = (meta.get("doi") or "").lower() or None
    rec = {"url": url, "doi": doi, "title": unfurl.get("title") or meta.get("title"), "abstract": unfurl.get("text") or meta.get("abstract"), "authors": [], "journal": unfurl.get("service_name") or "", "year": None, "pdf_url": meta.get("pdf")}
    if doi:
        cr = crossref(doi)
        if cr:
            rec.update({k: v for k, v in cr.items() if v})
        pm = pubmed_by_doi(doi)
        if pm:
            rec["pmid"] = pm["pmid"]; rec["pmcid"] = pm.get("pmcid")
            if pm.get("abstract") and (not rec.get("abstract") or len(rec["abstract"]) < 300):
                rec["abstract"] = pm["abstract"]
        oa = unpaywall(doi)
        if oa:
            rec["oa_url"] = oa
        rec["publisher_url"] = "https://doi.org/" + doi
    rec["title"] = re.sub(r"\s+", " ", rec.get("title") or "").strip() or url
    if rec.get("abstract"):
        rec["abstract"] = re.sub(r"\s+", " ", rec["abstract"]).strip()[:4000]
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="re-read the whole channel history (default: only messages newer than the last import)")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    token = os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_USER_TOKEN")
    if not token:
        sys.exit("SLACK_BOT_TOKEN is not set")
    anon = set(x for x in os.environ.get("JOURNAL_CLUB_ANON", "").split(",") if x)
    chan = find_channel(token, os.environ.get("SLACK_ARTICLES_CHANNEL", "articles"))
    team = slack("auth.test", token)
    store = json.load(open(OUT)) if OUT.exists() else {"updated": None, "channel": chan, "items": []}
    by_key = {(it.get("doi") or it["url"]): it for it in store["items"]}
    by_ts = {it["slack_ts"]: it for it in store["items"]}
    oldest = 0 if a.full or not store["items"] else max(float(it["slack_ts"]) for it in store["items"])
    # 1. messages
    msgs, cursor = [], None
    while True:
        j = slack("conversations.history", token, channel=chan, limit=200, oldest=oldest, **({"cursor": cursor} if cursor else {}))
        msgs += [m for m in j["messages"] if m.get("type") == "message" and not m.get("subtype") in ("channel_join", "channel_leave", "bot_message")]
        cursor = (j.get("response_metadata") or {}).get("next_cursor")
        if not cursor or not j.get("has_more"):
            break
    msgs.sort(key=lambda m: float(m["ts"]))
    if a.limit:
        msgs = msgs[-a.limit:]
    print(f"{len(msgs)} messages to look at")
    new = 0
    for m in msgs:
        urls = links_in(m)
        if not urls:
            continue
        unfurls = {x.get("original_url") or x.get("from_url") or x.get("title_link"): x for x in (m.get("attachments") or [])}
        for url in urls[:3]:
            rec = resolve(url, unfurls.get(url) or {})
            key = rec.get("doi") or url
            it = by_key.get(key)
            if not it:
                first = (rec.get("authors") or [""])[0].split(",")[0] or "shared"
                it = {"id": make_id(first, rec.get("year") or time.strftime("%Y", time.gmtime(float(m["ts"]))), rec["title"], set(x["id"] for x in store["items"])),
                      "slack_ts": m["ts"], "shared_on": time.strftime("%Y-%m-%d", time.gmtime(float(m["ts"]))), "shared_by": user_name(token, m.get("user"), anon),
                      "message": clean_text(m.get("text")), "comments": [], "reactions": []}
                it.update(rec); store["items"].append(it); by_key[key] = it; by_ts[m["ts"]] = it; new += 1
            it["permalink"] = it.get("permalink") or f"https://{team.get('url','').replace('https://','').rstrip('/')}/archives/{chan}/p{m['ts'].replace('.', '')}"
            if new and new % 15 == 0:
                json.dump(store, open(OUT, "w"), indent=1, ensure_ascii=False)  # checkpoint so an interrupted run keeps its work
            # 2. discussion: thread replies + reactions
            it["reactions"] = [{"name": r["name"], "count": r["count"]} for r in (m.get("reactions") or [])]
            if m.get("reply_count"):
                rep = slack("conversations.replies", token, channel=chan, ts=m["ts"], limit=200)["messages"][1:]
                it["comments"] = [{"by": user_name(token, r.get("user"), anon), "date": time.strftime("%Y-%m-%d %H:%M", time.gmtime(float(r["ts"]))), "text": clean_text(r.get("text"))} for r in rep if clean_text(r.get("text"))]
            time.sleep(0.4)
    from .jc_curate import curate
    curate([it for it in store["items"] if not it.get("kind")])
    # 3. tags
    if not a.no_llm and any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_FEDERATION_RULE_ID", "OPENAI_API_KEY")):
        from .classify import classify_record
        todo = [it for it in store["items"] if not it.get("tags") and it.get("kind", "paper") == "paper" and it.get("title") and not it.get("title_unresolved")]
        print(f"tagging {len(todo)} papers")
        failures = 0
        for n, it in enumerate(todo, 1):
            try:
                rec = {"id": it["id"], "title": it["title"], "authors": it.get("authors") or [], "journal": it.get("journal") or "", "year": it.get("year"), "abstract": it.get("abstract") or ""}
                classify_record(rec)
                for k in ("tags", "summary", "key_finding", "free_keywords", "classification"):
                    it[k] = rec.get(k)
                if n % 15 == 0:
                    json.dump(store, open(OUT, "w"), indent=1, ensure_ascii=False)
                failures = 0
            except Exception as e:
                failures += 1
                print("tagging failed", it["id"], e)
                if failures >= 3:
                    json.dump(store, open(OUT, "w"), indent=1, ensure_ascii=False)
                    raise SystemExit("tagging keeps failing; stopping so the error is visible")
                continue
    store["updated"] = time.strftime("%Y-%m-%d")
    store["items"].sort(key=lambda it: it["slack_ts"], reverse=True)
    json.dump(store, open(OUT, "w"), indent=1, ensure_ascii=False)
    print(f"{new} new papers; {len(store['items'])} total -> {OUT}")


if __name__ == "__main__":
    main()
