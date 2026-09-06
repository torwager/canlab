/* Community account: GitHub sign-in through the community API (worker/), synced "My list" and named lists.
   Sign-in does nothing until CANLAB_CONFIG.communityApi is set; named lists fall back to this browser's storage. */
window.CLAccount = (function () {
  const api = (window.CANLAB_CONFIG || {}).communityApi || "";
  const state = { user: null, ready: false };
  const MERGED_KEY = "canlab.mylist.merged";   // login of the account whose list was merged with this browser's
  const LISTS_KEY = "canlab.lists.v1";         // named lists when not signed in (or no API)
  const LISTS_MAX = 20, LIST_IDS_MAX = 2000;   // mirrors the worker's limits

  async function call(path, opts = {}) {
    const r = await fetch(api + path, { credentials: "include", headers: { "Content-Type": "application/json" }, ...opts });
    if (r.status === 401) return null;
    if (!r.ok) throw new Error("community API " + r.status);
    return r.json();
  }
  async function init() {
    if (!api) { state.ready = true; render(); return state; }
    try {
      const me = await call("/api/me");
      if (me) {
        state.user = me;
        // first sign-in on this browser: merge the local list into the account, then adopt the account list
        const local = [...CL.list.ids()];
        let stars = me.stars || [];
        if (local.length && localStorage.getItem(MERGED_KEY) !== me.login) {
          const merged = [...new Set([...stars, ...local])];
          const res = await call("/api/stars", { method: "PUT", body: JSON.stringify({ ids: merged }) });
          stars = (res && res.stars) || merged;
        }
        CL.list._ids = new Set(stars); CL.list.save();
        try { localStorage.setItem(MERGED_KEY, me.login); } catch (e) { /* ignore */ }
        // named lists: adopt the account's; if the account has none but this browser does, upload the local ones once
        const localLists = readLocalLists();
        if (Object.keys(me.lists || {}).length) writeLocalLists(me.lists);
        else if (Object.keys(localLists).length) { const res = await call("/api/lists", { method: "PUT", body: JSON.stringify({ lists: localLists }) }).catch(() => null); if (res && res.lists) { state.user.lists = res.lists; writeLocalLists(res.lists); } }
      }
    } catch (e) { console.warn("community API unavailable", e.message); }
    state.ready = true; render();
    return state;
  }
  // keep the account in sync with star clicks
  document.addEventListener("cl:star", e => { if (state.user && api) call("/api/star", { method: "POST", body: JSON.stringify({ id: e.detail.id, on: e.detail.on }) }).catch(() => {}); });
  function signIn() { location.href = api + "/auth/login?return=" + encodeURIComponent(location.href); }
  async function signOut() { try { await call("/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ } state.user = null; try { localStorage.removeItem(MERGED_KEY); } catch (e) { /* ignore */ } render(); }

  // ---- named lists: {name: [ids]}; account-backed when signed in, else localStorage. "stars" (CL.list) is the default list.
  function cleanLists(obj) {
    const out = {}; if (!obj || typeof obj !== "object") return out;
    for (const [name, ids] of Object.entries(obj)) {
      if (Object.keys(out).length >= LISTS_MAX) break;
      const n = String(name).trim(); if (!n) continue;
      out[n] = [...new Set((Array.isArray(ids) ? ids : []).filter(x => typeof x === "string" && x))].slice(0, LIST_IDS_MAX);
    }
    return out;
  }
  function readLocalLists() { try { return cleanLists(JSON.parse(localStorage.getItem(LISTS_KEY) || "{}")); } catch (e) { return {}; } }
  function writeLocalLists(obj) { try { localStorage.setItem(LISTS_KEY, JSON.stringify(obj)); } catch (e) { /* storage unavailable */ } }
  const lists = {
    async get() {
      if (state.user && api) {
        try { const res = await call("/api/lists"); if (res && res.lists) { state.user.lists = res.lists; writeLocalLists(res.lists); return res.lists; } } catch (e) { /* fall back to local copy */ }
      }
      return readLocalLists();
    },
    async save(obj) {
      const clean = cleanLists(obj);
      writeLocalLists(clean);
      if (state.user && api) {
        try { const res = await call("/api/lists", { method: "PUT", body: JSON.stringify({ lists: clean }) }); if (res && res.lists) { state.user.lists = res.lists; writeLocalLists(res.lists); return res.lists; } } catch (e) { console.warn("could not save lists to account", e.message); }
      }
      return clean;
    },
  };

  function render() {
    document.querySelectorAll("[data-account]").forEach(el => {
      if (!api) { el.innerHTML = el.dataset.account === "full" ? '<p class="muted small" style="margin:0">Accounts are not open yet. Your list is saved in this browser; use Export on the My list page to move it.</p>' : ""; return; }
      if (state.user) el.innerHTML = `<span class="small">Signed in as <b>${CL.esc(state.user.login)}</b> · your list is synced to your account.</span> <button class="btn link" data-signout>Sign out</button>`;
      else el.innerHTML = `<button class="btn primary" data-signin>Sign in with GitHub</button> <span class="small muted">Saves your list across devices and lets your stars count toward the community picks.</span>`;
    });
  }
  document.addEventListener("click", e => { if (e.target.closest("[data-signin]")) signIn(); if (e.target.closest("[data-signout]")) signOut(); });
  return { state, init, signIn, signOut, api, call, lists };
})();
document.addEventListener("DOMContentLoaded", () => { if (window.CL) CLAccount.init(); });
