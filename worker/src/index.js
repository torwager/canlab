/**
 * CANlab community API (Cloudflare Worker + KV).
 *
 * GET  /auth/login?return=<url>   start GitHub OAuth (state stored in KV for 10 min)
 * GET  /auth/callback             exchange code, create a session cookie (30 days), redirect back
 * POST /auth/logout               clear the session
 * GET  /api/me                    { login, avatar, stars: [...], lists: {...} } or 401
 * PUT  /api/stars   {ids:[...]}   replace the signed-in user's starred list (used to merge a browser list on first sign-in)
 * POST /api/star    {id, on}      add or remove one paper from the starred list
 * GET  /api/lists                 { lists: {name: [ids]} } the signed-in user's named lists (401 if not signed in)
 * PUT  /api/lists   {lists:{...}} replace the signed-in user's named lists (max 20 lists, 2000 ids each)
 * GET  /api/picks                 { updated, picks: [{id, n}] } most-starred papers (public, cached 5 min)
 *
 * "stars" is the default list: it is what the star buttons on the site toggle and what counts toward
 * community picks. Named lists ("lists") are private to the user and do not affect the picks.
 *
 * KV keys: state:<nonce> -> return url; sess:<token> -> {uid, login, avatar};
 *          user:<uid> -> {login, avatar, stars, lists, updated}; counts -> {paperId: n}.
 * Vars (wrangler.jsonc): SITE_ORIGIN (scheme+host, e.g. https://torwager.github.io), SITE_PATH (e.g. /canlab),
 *          GITHUB_CLIENT_ID. Secrets (wrangler secret put): GITHUB_CLIENT_SECRET.
 */
const SESSION_DAYS = 30;
const COOKIE = "canlab_session";
const USER_AGENT = "canlab-site";
const MAX_LISTS = 20;        // named lists per user
const MAX_LIST_IDS = 2000;   // ids per named list
const MAX_STARS = 5000;      // ids in the default (starred) list
const MAX_ID_LEN = 200;      // characters per paper id
const MAX_LIST_NAME = 80;    // characters per list name

/** Origins allowed to call the API with credentials (an Origin header is scheme+host only, no path). */
function allowedOrigins(env) {
  return [...new Set([env.SITE_ORIGIN, "https://torwager.github.io", "http://localhost:8765", "http://127.0.0.1:8765"].filter(Boolean))];
}
function cors(env, req, extra = {}) {
  const origin = req.headers.get("Origin");
  const h = { "Vary": "Origin", ...extra };
  if (origin && allowedOrigins(env).includes(origin)) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Access-Control-Allow-Credentials"] = "true";
    h["Access-Control-Allow-Methods"] = "GET,POST,PUT,OPTIONS";
    h["Access-Control-Allow-Headers"] = "Content-Type";
  }
  return h;
}
const json = (env, req, data, status = 200, extra = {}) => new Response(JSON.stringify(data), { status, headers: cors(env, req, { "Content-Type": "application/json; charset=utf-8", ...extra }) });
const rand = () => { const b = new Uint8Array(24); crypto.getRandomValues(b); return [...b].map(x => x.toString(16).padStart(2, "0")).join(""); };
const cookieOf = (req, name) => { const m = (req.headers.get("Cookie") || "").match(new RegExp("(?:^|;\\s*)" + name + "=([^;]+)")); return m ? m[1] : null; };
// SameSite=None because the site (github.io) and the API (workers.dev) are on different origins.
const sessionCookie = (token, maxAge) => `${COOKIE}=${token}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure; SameSite=None`;

async function session(env, req) {
  const t = cookieOf(req, COOKIE);
  if (!t) return null;
  return env.STORE.get("sess:" + t, "json");
}
async function user(env, uid) { return (await env.STORE.get("user:" + uid, "json")) || { stars: [], lists: {} }; }
async function saveUser(env, uid, u) { u.updated = new Date().toISOString(); await env.STORE.put("user:" + uid, JSON.stringify(u)); }
async function bumpCounts(env, changes) {
  // changes: {paperId: +1|-1}. Read-modify-write; fine at this site's scale.
  const counts = (await env.STORE.get("counts", "json")) || {};
  for (const [id, d] of Object.entries(changes)) { counts[id] = (counts[id] || 0) + d; if (counts[id] <= 0) delete counts[id]; }
  await env.STORE.put("counts", JSON.stringify(counts));
}

/** Where to send the browser after sign-in: only back to an allowed origin, else the account page on the site. */
function defaultReturn(env) { return env.SITE_ORIGIN + (env.SITE_PATH || "") + "/account.html"; }
function safeReturn(env, url) {
  try { const u = new URL(url); if (allowedOrigins(env).includes(u.origin)) return u.toString(); } catch (e) { /* fall through */ }
  return defaultReturn(env);
}

/** Validate a list of paper ids: strings only, bounded length, de-duplicated, capped. */
function cleanIds(ids, max) {
  return [...new Set((Array.isArray(ids) ? ids : []).filter(x => typeof x === "string" && x.length > 0 && x.length <= MAX_ID_LEN))].slice(0, max);
}
/** Validate a {name: [ids]} object of named lists. Drops empty/invalid names, caps list count and size. */
function cleanLists(lists) {
  const out = {};
  if (!lists || typeof lists !== "object" || Array.isArray(lists)) return out;
  for (const [name, ids] of Object.entries(lists)) {
    if (Object.keys(out).length >= MAX_LISTS) break;
    const n = String(name).trim();
    if (!n || n.length > MAX_LIST_NAME) continue;
    out[n] = cleanIds(ids, MAX_LIST_IDS);
  }
  return out;
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env, req) });
    try {
      // ---- auth
      if (url.pathname === "/auth/login") {
        const state = rand();
        await env.STORE.put("state:" + state, safeReturn(env, url.searchParams.get("return") || ""), { expirationTtl: 600 });
        const gh = new URL("https://github.com/login/oauth/authorize");
        gh.searchParams.set("client_id", env.GITHUB_CLIENT_ID);
        gh.searchParams.set("redirect_uri", url.origin + "/auth/callback");
        gh.searchParams.set("state", state);
        gh.searchParams.set("scope", "read:user");
        return Response.redirect(gh.toString(), 302);
      }
      if (url.pathname === "/auth/callback") {
        const state = url.searchParams.get("state") || "", code = url.searchParams.get("code") || "";
        const ret = await env.STORE.get("state:" + state);
        if (!ret || !code) return new Response("Sign-in link expired. Please try again.", { status: 400 });
        ctx.waitUntil(env.STORE.delete("state:" + state));
        // Exchange the code for an access token, use it once to read the public profile, then discard it.
        const tok = await fetch("https://github.com/login/oauth/access_token", { method: "POST", headers: { "Accept": "application/json", "Content-Type": "application/json", "User-Agent": USER_AGENT },
          body: JSON.stringify({ client_id: env.GITHUB_CLIENT_ID, client_secret: env.GITHUB_CLIENT_SECRET, code, redirect_uri: url.origin + "/auth/callback" }) });
        const tj = await tok.json();
        if (!tj.access_token) return new Response("GitHub did not return a token.", { status: 502 });
        const gu = await (await fetch("https://api.github.com/user", { headers: { "Authorization": "Bearer " + tj.access_token, "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json" } })).json();
        if (!gu.id) return new Response("Could not read your GitHub profile.", { status: 502 });
        const uid = String(gu.id);
        const u = await user(env, uid); u.login = gu.login; u.avatar = gu.avatar_url; await saveUser(env, uid, u);
        const token = rand();
        await env.STORE.put("sess:" + token, JSON.stringify({ uid, login: gu.login, avatar: gu.avatar_url }), { expirationTtl: SESSION_DAYS * 86400 });
        return new Response(null, { status: 302, headers: { "Location": ret, "Set-Cookie": sessionCookie(token, SESSION_DAYS * 86400) } });
      }
      if (url.pathname === "/auth/logout" && req.method === "POST") {
        const t = cookieOf(req, COOKIE);
        if (t) await env.STORE.delete("sess:" + t);
        return json(env, req, { ok: true }, 200, { "Set-Cookie": sessionCookie("", 0) });
      }

      // ---- public
      if (url.pathname === "/api/picks") {
        const counts = (await env.STORE.get("counts", "json")) || {};
        const picks = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 200).map(([id, n]) => ({ id, n }));
        return json(env, req, { updated: new Date().toISOString(), picks }, 200, { "Cache-Control": "public, max-age=300" });
      }

      // ---- signed-in only
      const s = await session(env, req);
      if (!s) return json(env, req, { error: "not signed in" }, 401);
      if (url.pathname === "/api/me") {
        const u = await user(env, s.uid);
        return json(env, req, { login: s.login, avatar: s.avatar, stars: u.stars || [], lists: u.lists || {} });
      }
      if (url.pathname === "/api/stars" && req.method === "PUT") {
        const body = await req.json();
        const ids = cleanIds(body.ids, MAX_STARS);
        const u = await user(env, s.uid); const before = new Set(u.stars || []); const after = new Set(ids);
        const changes = {}; for (const id of after) if (!before.has(id)) changes[id] = 1; for (const id of before) if (!after.has(id)) changes[id] = -1;
        u.stars = ids; await saveUser(env, s.uid, u); if (Object.keys(changes).length) await bumpCounts(env, changes);
        return json(env, req, { stars: u.stars });
      }
      if (url.pathname === "/api/star" && req.method === "POST") {
        const { id, on } = await req.json();
        if (typeof id !== "string" || !id.length || id.length > MAX_ID_LEN) return json(env, req, { error: "bad id" }, 400);
        const u = await user(env, s.uid); const set = new Set(u.stars || []); const had = set.has(id);
        if (on) set.add(id); else set.delete(id);
        u.stars = [...set]; await saveUser(env, s.uid, u);
        if (had !== !!on) await bumpCounts(env, { [id]: on ? 1 : -1 });
        return json(env, req, { stars: u.stars });
      }
      if (url.pathname === "/api/lists" && req.method === "GET") {
        const u = await user(env, s.uid);
        return json(env, req, { lists: u.lists || {} });
      }
      if (url.pathname === "/api/lists" && req.method === "PUT") {
        // Whole-object replace (the client owns the merge). Named lists never touch the community counts.
        const body = await req.json();
        const u = await user(env, s.uid);
        u.lists = cleanLists(body.lists);
        await saveUser(env, s.uid, u);
        return json(env, req, { lists: u.lists });
      }
      return json(env, req, { error: "not found" }, 404);
    } catch (e) {
      console.error(JSON.stringify({ level: "error", path: url.pathname, message: e.message }));
      return json(env, req, { error: "server error" }, 500);
    }
  },
};
