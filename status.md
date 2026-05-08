# Status — worldmachines

## Active
- Site live and taking submissions at worldmachines.org
- 60 articles in website/content/articles/ (22 contributions, 38 resources/books)
- Repo reorganized into raw-notes/, wiki/, and website/ collaboration zones

## Upcoming

### Near-term
- **Fix incorrect book publication dates** — 7 books got edition/translation dates from Open Library rather than true first-publication years. Manual fix needed:
  - Divine Comedy: 2015 → ~1308
  - Don Quixote: 1747 → 1605
  - Revolt of the Masses: 2021 → 1930
  - Monkey King: Journey to the West: 2012 → ~1592
  - Candide: 1746 → 1759
  - The Complete Essays (Montaigne): 1958 → 1580
  - A Distant Mirror: 1600 → 1978
- **Add dates for 7 books not found by Open Library** — Ibn Khaldun: An Intellectual Biography, Islamic Gunpowder Empires, Majapahit, Raiders Rulers and Traders, The Chivalric Turn, The Printing Revolution in Early Modern Europe, Venice: A New History
- **Update site blurb** — blurbs.md could use richer prose explaining world machines theory

### Later
- Article detail pages — surface extracted full text for reading on-site
- Oracle page — AI backend layer using stored full text for analysis, synthesis, modeling
- Filtering/search by contributor or format
- Consider pagination or grouping as article count grows
- Add www → worldmachines.org redirect

## Done

- **2026-05-07** — Reorganized repo into `raw-notes/`, `wiki/`, and `website/`; moved Cloudflare Pages app under `website/`; added CODEOWNERS/review-policy docs
- **2026-05-04** — Added /profile + /api/profile to Cloudflare Access policy (collaborator email allowlist); tested working
- **2026-05-04** — Backfilled first-publication years for 31/38 books via Open Library API (`scripts/backfill_book_dates.py`)
- **2026-05-04** — Backfilled actual publication dates for all 22 essay/contribution articles via trafilatura (`scripts/backfill_dates.py`)
- **2026-05-04** — Split `type` (contribution|resource) from `format` (essay|short story|paper|book); added format dropdown to submit form
- **2026-05-04** — Moved contributions off front page to `/contributions`; renamed bibliography to `/resources`; front page is now blurb-only landing page
- **2026-05-04** — Standalone `/profile` page for editing name/url/bio (handle+email readonly); linked from submit page greeting
- **2026-05-04** — Submit page: greets submitter by name after Access login; "Edit profile" link
- **2026-05-04** — Contributors page: links website instead of name
- **2026-05-04** — Comprehensive CSS style overhaul; nav visually attached to header as one block
- **2026-05-04** — KV value format upgraded from plain handle string to JSON `{handle, name, url, bio}`
- **2026-05-04** — Oracle page stub added to nav
- **2026-05-04** — Batch-populated 60 articles from spreadsheet data (books as resources, essays as contributions)
- **2026-05-04** — Contributors added to handle registry via `/admin/handles` web UI
- **2026-05-04** — Full pipeline live and tested end-to-end (form → Access → Function → GH Actions → Pages deploy)
- **2026-05-04** — Handle registry: email→{handle,name,url,bio} KV lookup; `/admin/handles` web UI (Access-protected, admin-only)
- **2026-05-04** — Cloudflare Access: `/submit` + `/api/submit` gated for approved collaborators; `/admin*` gated for admin only
- **2026-05-04** — Custom domain worldmachines.org live on Cloudflare Pages
- **2026-05-04** — GitHub org at github.com/worldmachines, repo worldmachines/worldmachines
- **2026-05-04** — Project initiated: folder, CLAUDE.md, status.md, git repo, dashboard registration
