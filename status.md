# Status — worldmachines

## Active
- Testing end-to-end submission pipeline with initial collaborators

## Upcoming

### Near-term
- **Batch populate from spreadsheet** — write a script that reads a CSV/spreadsheet of existing links and fires `repository_dispatch` for each, or writes article JSONs directly and runs `build.py`
- **Update site blurb** — the tagline/description on the index page needs proper copy explaining what world machines theory is and what this site is for
- **Add URL + bio to handle registry** — extend the KV value (or use a separate KV key) to store each contributor's personal URL and short bio alongside their handle; update `/admin/handles` form to capture these fields
- **Contributors page** — `worldmachines.org/contributors` listing all handles with their bio and URL, each linking to a filtered view of their submissions (or an anchor in the article list)

### Later
- Article detail pages — surface extracted full text for reading on-site
- Filtering/search by type (Contribution vs Resource) or contributor
- AI backend layer — use stored full text for analysis, synthesis, modeling
- Consider pagination or grouping as article count grows
- Add www → worldmachines.org redirect

## Done
- **2026-05-04** — Contributors added to handle registry via `/admin/handles` web UI
- **2026-05-04** — Full pipeline live and tested end-to-end (form → Access → Function → GH Actions → Pages deploy)
- **2026-05-04** — Handle registry: email→handle KV lookup replaces name field on submit form; `/admin/handles` web UI (Access-protected, admin-only)
- **2026-05-04** — Cloudflare Access: `/submit` + `/api/submit` gated for approved collaborators; `/admin*` gated for admin only
- **2026-05-04** — Custom domain worldmachines.org live on Cloudflare Pages
- **2026-05-04** — GitHub org at github.com/worldmachines, repo worldmachines/worldmachines
- **2026-05-04** — Project initiated: folder, CLAUDE.md, status.md, git repo, dashboard registration
