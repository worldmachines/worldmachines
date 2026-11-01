# blyg-shell

`wm-blyg-shell` is the Cloudflare Worker that puts the worldmachines.org site bar
on [blyg.worldmachines.org](https://blyg.worldmachines.org/).

The blyg runs on Blygger Studio, a separate Worker named `blyg-blyg-worldmachines-org`
(source and deploy config in `~/Code/worldmachines-related/wm-blyg`, deployed
with `wrangler.private.jsonc`). Studio has no hook for public page markup, and we
do not fork it. This Worker owns the custom domain and does three things:

1. It forwards every request to Studio unchanged through the `STUDIO` service
   binding: method, headers, body, cookies and URL, host included.
2. It returns every non-page response untouched: `/studio`, `/api`, feeds,
   JSON, media and errors.
3. On public HTML pages, which means GET or HEAD, a 200 response with
   `text/html`, and a path outside the excluded list in `src/index.ts`, it
   makes two additions with HTMLRewriter:
   - it appends `<link rel="stylesheet" href="https://worldmachines.org/nav.css">`
     to `<head>`;
   - it prepends the partial `https://worldmachines.org/partials/sitenav-blyg.html`
     inside `<body>`, before Studio's `div.blyg`.

`website/scripts/build.py` generates both files, and they deploy with the
site. Change the nav in `NAV_GROUPS` or in the `@nav-css` block of
`website/style.css`, rebuild, and deploy the site. The blyg picks up the change
within about 5 minutes (300 s edge cache plus a 60 s in-isolate memo), and this
Worker does not need a redeploy.

## Caching and validators

- The partial is fetched with `cf.cacheTtl` = `NAV_CACHE_TTL` (300 s).
- The ETag is Studio's ETag with the nav's version added: `W/"<studio-hash>-nav<12 hex>"`.
  When the nav changes, the ETag changes too, so a 304 cannot hide a nav change.
  This Worker strips `If-None-Match` and `If-Modified-Since` before forwarding a
  page request, because Studio would otherwise answer a 304 to a pre-nav ETag.
  It then answers 304s itself.
- Studio's `Cache-Control`, `Cloudflare-CDN-Cache-Control`, `Link` and
  `Vary` headers are passed through as they are. `Content-Length` is dropped
  on rewritten pages. `X-WM-Nav` carries the nav version for debugging.
- If the partial cannot be fetched (error, timeout, non-200, or anything that
  does not start with `<div class="wm-sitechrome">`, such as Pages' index.html
  fallback), the page is served unmodified. A failure is remembered for 15 s.
- **Kill switch:** set `NAV_PARTIAL_URL` to `""`. Every request then passes
  through untouched.

## Tests

```sh
cd blyg-shell
npm install
npm test          # vitest in workerd, stub STUDIO binding
npm run typecheck
```

## Local end-to-end

You need three processes: the site, a Studio, and the shell.

```sh
# 1. the site, after `python3 scripts/build.py` in website/
python3 -m http.server 8788 --bind 127.0.0.1 -d website

# 2. a stock Studio checkout (worker name "blyg"), with no AI binding
cd <studio-checkout> && npx wrangler dev --local --port 8811 --inspector-port 9331

# 3. the shell, bound to that Studio through the local dev registry
cd blyg-shell && npx wrangler dev -c wrangler.local.jsonc --port 8812 --local
```

Then open http://127.0.0.1:8812/.

## Cut-over

The custom domain `blyg.worldmachines.org` is held by the Studio worker now. A
custom domain can be attached to only one Worker. When `wrangler deploy` finds
the domain on another Worker, it asks to move it in an interactive terminal.
In a non-interactive run (CI, or a script that pipes stdout) it **moves the
domain without asking**. So whichever Worker last deployed with the route
holds the domain. That is why step 2 matters.

1. **Ship the site first.** Merge this branch and deploy worldmachines.org.
   Then check both files:
   ```sh
   curl -sI https://worldmachines.org/nav.css | head -1
   curl -sL https://worldmachines.org/partials/sitenav-blyg.html | head -2   # must start <div class="wm-sitechrome">
   ```
   Pages may 308 `…/sitenav-blyg.html` to `…/sitenav-blyg`. The Worker follows
   the redirect.

2. **Take the route out of Studio's config** so that no later Studio deploy
   can take the domain back. In `~/Code/worldmachines-related/wm-blyg/wrangler.private.jsonc`,
   delete lines 32–35 (and the blank line 31 or 36):
   ```jsonc
     "routes": [
       // A Custom Domain provisions its own DNS — nothing to add by hand.
       { "pattern": "blyg.worldmachines.org", "custom_domain": true }
     ],
   ```
   In the same place, add the following lines so Studio is reachable only
   through the shell (no nav-less copy on `*.workers.dev`):
   ```jsonc
     "workers_dev": false,
     "preview_urls": false,
   ```
   Commit that in wm-blyg. Deploying Studio is optional at this point. A
   deploy with no `routes` does not detach a domain the Worker already holds.
   It only stops the Worker from claiming the domain again.

3. **Optional dry run on workers.dev:**
   ```sh
   cd blyg-shell && npx wrangler deploy --env preview
   curl -s https://wm-blyg-shell-preview.<your-subdomain>.workers.dev/ | grep -c wm-sitechrome
   ```
   Studio builds its links from its `site_url` setting, so they still point at
   blyg.worldmachines.org. Remove the preview afterwards with
   `npx wrangler delete --name wm-blyg-shell-preview`.

4. **Move the domain.** Run this from a real terminal:
   ```sh
   cd blyg-shell && npx wrangler deploy --env=""
   ```
   Answer **yes** to "Custom Domains already exist … Update them to point to
   this script instead?". The domain moves over without a gap.

5. **Verify:**
   ```sh
   curl -s https://blyg.worldmachines.org/ | grep -c 'class="wm-sitechrome"'     # 1
   curl -sI https://blyg.worldmachines.org/ | grep -i -E '^(etag|x-wm-nav)'        # …-nav<hex>
   curl -s https://blyg.worldmachines.org/feed.xml | head -c 60                     # <?xml …
   curl -s -o /dev/null -w '%{http_code}\n' https://blyg.worldmachines.org/studio  # as before
   ```
   Then sign in to `/studio`, and run one `wm-blyg` `npm run deploy:all`
   verification (its verify URLs go through the shell).

## Rollback

You can roll back three ways, from fastest to most complete:

- **Nav only:** `npx wrangler deploy --env="" --var NAV_PARTIAL_URL:` in
  `blyg-shell/`. The shell stays in front and every response is Studio's own.
  Redeploying without the flag restores the nav.
- **Give the domain back to Studio:** in wm-blyg, restore the `routes` block
  above (and remove `workers_dev: false` if you want workers.dev back), then
  run `npx wrangler deploy --config wrangler.private.jsonc` (or
  `npm run deploy:all`) and answer yes to moving the domain. Or, in the
  dashboard, go to Workers & Pages → blyg-blyg-worldmachines-org → Settings →
  Domains & Routes → Add → Custom domain → `blyg.worldmachines.org`.
- **Then retire the shell:** delete the `routes` entry from `blyg-shell/wrangler.jsonc`
  (otherwise a later shell deploy would take the domain again) and run
  `npx wrangler delete --name wm-blyg-shell` when you are sure.

## Notes

- **Crons stay on Studio.** Studio's three cron triggers are on its own Worker
  and do not depend on the domain. The shell has no `scheduled` handler.
- **Auth.** Cookies, OAuth redirects (`/studio/auth/...`) and bearer-token calls
  to `/api` pass through byte for byte. Studio sees the original URL and host,
  so its HTTPS checks and `siteOrigin` behave as before.
- **Studio's own cache.** Studio caches public HTML in its `PublicHtml`
  entrypoint, and that cache still works behind the service binding. The shell
  rewrites a streamed copy and adds no cache layer of its own.
- **Static export.** Studio's static export fetches its own routes. If it is
  pointed at `https://blyg.worldmachines.org`, the exported HTML includes the
  nav, with absolute links to worldmachines.org and the nav.css link.
