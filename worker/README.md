# Community API (Cloudflare Worker)

GitHub sign-in, synced "My list", named lists and community picks for the CANlab site (https://torwager.github.io/canlab). Free tier is ample (100k requests/day, 1 GB KV).

The site works without it: until `communityApi` is set in `site/assets/config.js`, lists are kept in the browser only.

## One-time setup (about 10 minutes)

The worker's URL is `https://canlab-community.<account>.workers.dev`, where `<account>` is your Cloudflare workers.dev subdomain (shown in the dashboard under Workers & Pages, and printed by `wrangler deploy`).

1. **GitHub OAuth App** (https://github.com/settings/developers → OAuth Apps → New):
   - Application name: CANlab · Homepage: https://torwager.github.io/canlab
   - Authorization callback URL: `https://canlab-community.<account>.workers.dev/auth/callback`
   - Copy the Client ID; generate a Client Secret and copy it.
2. **Cloudflare**, from this folder:
   ```bash
   cd worker && npm install
   npx wrangler login                                  # opens the browser once
   npx wrangler kv namespace create STORE              # prints an id → paste into wrangler.jsonc ("id")
   # paste the GitHub Client ID into wrangler.jsonc ("GITHUB_CLIENT_ID")
   npx wrangler secret put GITHUB_CLIENT_SECRET        # paste the secret when prompted
   npx wrangler deploy                                 # prints the workers.dev URL
   ```
   If you do not yet know your workers.dev subdomain, deploy first, then fill in the callback URL in the GitHub OAuth App.
3. Copy the workers.dev URL (no trailing slash) into `site/assets/config.js` as `communityApi: "https://canlab-community.<account>.workers.dev"` and push.

The site then shows "Sign in with GitHub" on the Account and My list pages. Stars sync to the account, the browser list is merged in on first sign-in, named lists are saved to the account, and the community picks endpoint ranks the most-starred papers.

### Custom domain (optional)
If the site later moves to a domain on Cloudflare DNS, uncomment the `routes` example in `wrangler.jsonc` (e.g. `community.canlab.science`), redeploy, and update both the GitHub OAuth callback URL and `communityApi`. Add the new site origin to `SITE_ORIGIN` in `wrangler.jsonc` (github.io and localhost stay allowed in `src/index.js`).

### Local development
`npx wrangler dev` runs the worker on http://localhost:8787. Serve the site on port 8765 (`python3 -m http.server 8765` in `site/`) and point `communityApi` at the dev URL; `http://localhost:8765` and `http://127.0.0.1:8765` are allowed origins.

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/auth/login?return=<url>` | Start GitHub OAuth; `return` must be on an allowed origin |
| GET | `/auth/callback` | OAuth callback; sets the session cookie and redirects back |
| POST | `/auth/logout` | Clear the session |
| GET | `/api/me` | `{login, avatar, stars, lists}` or 401 |
| PUT | `/api/stars` `{ids}` | Replace the starred list |
| POST | `/api/star` `{id, on}` | Star or unstar one paper |
| GET | `/api/lists` | `{lists: {name: [ids]}}` named lists |
| PUT | `/api/lists` `{lists}` | Replace named lists (max 20 lists, 2000 ids each) |
| GET | `/api/picks` | `{updated, picks: [{id, n}]}` most-starred papers, public, cached 5 min |

## Data and privacy
Stored per user: GitHub numeric id, login, avatar URL, the starred list, named lists, and last update time. No email, no password, no GitHub token is retained (the access token is used once to read the public profile and discarded). Sessions are random 192-bit tokens in an HttpOnly, Secure, SameSite=None cookie on the API domain, valid 30 days. Sign-out deletes the session. Community picks are aggregate star counts only; named lists are private and do not contribute to them. To delete an account's data, remove its `user:<id>` key from the KV namespace (Cloudflare dashboard or `npx wrangler kv key delete`).
