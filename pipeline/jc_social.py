"""Find the paper behind an X/Twitter or Bluesky post shared in the journal club.

People often share a paper by posting the author's announcement rather than the paper itself. For such a link
we read the post through public, no-login endpoints and return the paper links it contains:
  X/Twitter: X's own embed service (cdn.syndication.twimg.com/tweet-result, the endpoint behind embedded
             tweets), which returns the tweet with fully expanded links, plus links in a quoted tweet.
  Bluesky:   the public AppView API (public.api.bsky.app): link facets, the link card, a quoted post, and the
             author's own replies in the thread (announcements often put the link in the first reply).
Short links (t.co, buff.ly, bit.ly, ...) are followed. Only links that look like papers (a DOI or a known
publisher/preprint host) are returned. If the post has no paper link, a title in quotation marks or the
first line of the post is tried against Crossref and accepted only on a near-exact title match.
The post's text is used in memory only and is never saved.
"""
import re
import urllib.parse

import requests

from .jc_curate import PAPER_HOSTS, crossref_title_match, decode_redirect, doi_from_url, host

UA = {"User-Agent": "Mozilla/5.0 (canlab-site journal club)"}
SHORTENERS = ("t.co", "buff.ly", "bit.ly", "ow.ly", "dlvr.it", "lnkd.in", "tinyurl.com", "goo.gl", "rdcu.be", "trib.al", "shorturl.at", "go.nature.com", "cell.com/action/showPdf")
X_RE = re.compile(r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/[^/]+/status(?:es)?/(\d+)", re.I)
BSKY_RE = re.compile(r"https?://(?:www\.)?bsky\.app/profile/([^/]+)/post/([A-Za-z0-9]+)", re.I)


def kind(url):
    if X_RE.match(url or ""):
        return "x"
    if BSKY_RE.match(url or ""):
        return "bluesky"
    return None


def _expand(u):
    u = (u or "").strip()
    if not u.startswith("http"):
        return None
    if any(host(u) == s or host(u).endswith("." + s) for s in SHORTENERS):
        try:
            u = requests.head(u, headers=UA, allow_redirects=True, timeout=20).url
        except Exception:
            try:
                u = requests.get(u, headers=UA, allow_redirects=True, timeout=20, stream=True).url
            except Exception:
                return None
    return decode_redirect(u).split("?utm")[0]


def _paperish(u):
    return bool(u) and not kind(u) and (bool(doi_from_url(u)) or any(host(u).endswith(h) for h in PAPER_HOSTS))


def _x_post(tid):
    try:
        d = requests.get("https://cdn.syndication.twimg.com/tweet-result", params={"id": tid, "token": "a"}, headers=UA, timeout=20).json()
    except Exception:
        return [], ""
    urls = [u.get("expanded_url") for u in (d.get("entities") or {}).get("urls", [])]
    q = d.get("quoted_tweet") or {}
    urls += [u.get("expanded_url") for u in (q.get("entities") or {}).get("urls", [])]
    return urls, (d.get("text") or "") + "\n" + (q.get("text") or "")


def _bsky_links(post):
    r = post.get("record") or {}
    urls = [f.get("uri") for fc in r.get("facets", []) for f in fc.get("features", []) if f.get("uri")]
    for e in (post.get("embed") or {}, r.get("embed") or {}):
        urls.append((e.get("external") or {}).get("uri"))
        rec = e.get("record") or {}
        rec = rec.get("record", rec)  # recordWithMedia nests one level deeper
        urls.append(((rec.get("embeds") or [{}])[0].get("external") or {}).get("uri") if rec.get("embeds") else None)
        v = rec.get("value") or {}
        urls += [f.get("uri") for fc in v.get("facets", []) for f in fc.get("features", []) if f.get("uri")]
    return [u for u in urls if u], r.get("text") or ""


def _bsky_post(handle, rkey):
    api = "https://public.api.bsky.app/xrpc/"
    try:
        did = handle if handle.startswith("did:") else requests.get(api + "com.atproto.identity.resolveHandle", params={"handle": handle}, timeout=20).json()["did"]
        t = requests.get(api + "app.bsky.feed.getPostThread", params={"uri": f"at://{did}/app.bsky.feed.post/{rkey}", "depth": 1, "parentHeight": 0}, timeout=20).json()["thread"]
    except Exception:
        return [], ""
    urls, text = _bsky_links(t.get("post") or {})
    for rep in t.get("replies") or []:  # the author's own replies continue the announcement
        p = rep.get("post") or {}
        if (p.get("author") or {}).get("did") == did:
            u2, t2 = _bsky_links(p)
            urls += u2
            text += "\n" + t2
    return urls, text


def paper_links(url):
    """Paper URLs found in the post at `url` (empty if none). The post text is not returned."""
    if kind(url) == "x":
        urls, text = _x_post(X_RE.match(url).group(1))
    elif kind(url) == "bluesky":
        m = BSKY_RE.match(url)
        urls, text = _bsky_post(m.group(1), m.group(2))
    else:
        return []
    out = []
    for u in urls:
        u = _expand(u)
        if _paperish(u) and u not in out:
            out.append(u)
    if out:
        return out
    # No link: maybe the post quotes the title. Accept only a near-exact Crossref title match.
    cands = re.findall(r"[\"“]([^\"”]{25,250})[\"”]", text) + [text.strip().split("\n")[0]]
    for c in cands:
        meta = crossref_title_match(c.strip())
        if meta:
            return ["https://doi.org/" + meta["doi"]]
    return []
