<!--
  Prepend new entries at the top. Format:  ## YYYY-MM-DD · handle
  Keep entries to 1–3 sentences: what changed and why it matters for the project.
  For trivial commits (typos, config tweaks), add [trivial] to the commit message
  instead of writing an entry here.
-->

## 2026-08-05 · aneesh
Shipped member login and closed two auth holes. `/api/admin/handles` (the contributor registry, emails included) was reachable unauthenticated because the old Access policy covered `/admin/*` but not `/api/admin/*`; it now enforces an admin allowlist in-function, fail-closed. Worse, every member endpoint would also accept an email read from the *unverified* `CF_Authorization` cookie payload — a client-forgeable identity — so identity now flows through one shared library (`functions/_lib/access.js`) that cryptographically verifies the Access JWT when `ACCESS_TEAM_DOMAIN` is configured. The Witness/MCP panel gains a real "Sign in" button, sign-out, and self-service token list/revoke; a new `scripts/provision-access.mjs` creates the members + admin Access applications idempotently from the command line.

## 2026-07-27 · aneesh (2)
Expanded the Evolution guide with a substantial Biology toolkit that teaches DNA, genes, traits, inheritance, populations, variation, selection, drift, and ancestry before the advanced material. Added `/evolution/dennett`, a wide-ranging 2026 companion to *Darwin’s Dangerous Idea* that connects contemporary evolutionary science with consciousness, agency, culture, AI, meaning, ethics, and a carefully sourced constellation of successors and critics—including explicit World Machines guardrails against historical fatalism and simplistic memetics.

## 2026-07-27 · aneesh
Added **Evolution** to the site navigation and reshaped `/evolution/` into an easy-to-browse field reference for the *Darwin’s Dangerous Idea* book club rather than a formal course. The new topic guide opens with a plain-language causal map, lets readers enter by question, moves technical model details behind optional disclosures, improves keyboard/mobile access, and retains simulations, a glossary, and expert sources for deeper dives.

## 2026-07-24 · aneesh
Moved the `worldmachines.org` registration from Venkat's Cloudflare account to Aneesh's, completing the custom-domain cutover left pending since the July 16 bindings flip. The EPP auth-code route was a dead end — the domain was already at Cloudflare Registrar, so there was no registrar-to-registrar transfer to make and the zone could never leave `pending` in the receiving account; the working path is Cloudflare's inter-account transfer, which the *source* account initiates and the target accepts within five days. That move carries WHOIS contacts only, so the zone arrived holding stale A/AAAA records Cloudflare had auto-imported from Venkat's proxied DNS — all Cloudflare-owned IPs, which trips error 1000 and took the site down until they were deleted and the Pages custom domain provisioned its own proxied apex CNAME to `worldmachines-2rd.pages.dev`. Oracle, MCP, and every binding were unaffected: they already lived in Aneesh's account.

## 2026-07-17 · aneesh
Updated the `approval-policy` workflow so website/ changes can be approved by **either** @aneeshsathe or @vgururao (previously @vgururao only), and added an author-bypass: because GitHub blocks a PR author from approving their own PR, an owner who *opens* a website/ or wiki/ PR now self-clears that gate — otherwise an owner could never merge their own gated PR. Reflects the stack's move to Aneesh's account while keeping Venkat as a co-owner of the site gate. (This PR itself still requires Venkat's approval, since it touches website/ under the current policy.)

## 2026-07-16 · aneesh (2)
Put the Oracle's running costs on the Oracle page. A collapsible "health stats" box above the chat reports questions answered and dollars spent, split web vs MCP, against the hourly/daily spend caps that keep a public Oracle affordable — served by a new `/api/stats` Pages Function proxying the Oracle worker. The meter fails soft by design: any upstream trouble hides the box entirely rather than showing a broken number, so the chat is never blocked by its own dashboard. Asking a question now refreshes the numbers, and hitting a spend cap returns a plain-language "try again later" instead of an HTTP error.

## 2026-07-16 · aneesh
Consolidated the Oracle-page, MCP, and account-cutover work into one PR (supersedes #17, #20, #23). The Oracle at `/oracle` is now multi-turn chat with clean citations — `[chunk:…]` passages collapse into per-book "Sources" chips and concept `[[…]]` links become explorable buttons, so answers read as prose instead of raw tokens. Adds a public `/mcp` page (documenting the no-auth Oracle MCP + a gated Witness-token mint via `/api/mcp-token`, `MCP_TOKENS` KV) and flips the Pages bindings back to Aneesh's account (`HANDLES` namespace + `ORACLE_URL` → `wm-oracle-dev.aneeshsathe.workers.dev`); merging is itself the corrective cutover deploy. Also points the "Project Chat" nav link (every page + `build.py`'s template) at the project Discord (`discord.gg/tqUFztN3r`) instead of the old Zulip server.

## 2026-07-06 · vgr
Completed the Oracle/Witness stack transfer from Aneesh's Cloudflare account to Venkat's, and reorganized all five project repos into a single `worldmachines/` container folder (wm-site, wm-infra, wm-oracle, wm-encyclopedia-kb, wm-feeder). The full deploy: R2 buckets provisioned, catalog workers deployed via GitOps CI, 817 notes synced and embedded into both shared and personal DuckLake catalogs, Witness and Oracle workers stood up with fresh credentials, and PR #15 merged — bringing server-side `/api/ask` proxy, citation-enabled oracle.html, and the feeder ingest workflow. Oracle is now fully live on Venkat's account at worldmachines.org.

## 2026-06-10 · aneesh
Embedding correctness fix for the Oracle preview: EmbeddingGemma's asymmetric prefixes are now applied on both sides — documents in the notes pipeline (`title: … | text: …`) and queries in `/api/embed` (`task: search result | query: …`). Until now both embedded bare text, costing retrieval quality. Merging triggers a full re-embed of the notes parquet (758 notes) via `notes-ingest.yml`. Part of the wm-encyclopedia-kb Oracle/Witness (ADR 0002) Phase 1 work.

## 2026-05-30 · vgr
Three things shipped today. (1) **Full-text library**: new `worldmachines-library` R2 bucket serves PDFs under `public/` (open) and `private/` (CF Access JWT gated); article JSON schema gained `license` and `pdf_key` fields; resources page shows download badges and dynamically loads a Team Library section for registered members. First document: Darnton's _The Business of Enlightenment_ (CC BY), plus a companion supplement of all 1,197 French passages translated into English with page and chapter context (viewable at `/supplements/business-of-enlightenment-translations`). (2) **Self-service join flow**: CF Access can now be set to allow any email OTP; unregistered users who authenticate see a "not registered" panel redirecting to `/join`, where they submit a request that creates a GitHub issue with the exact `wrangler kv` approval command — one admin step instead of two. New `/api/me` endpoint provides consistent auth state across submit, profile, and library pages. (3) **ADR 0002** ([PR #13](https://github.com/worldmachines/worldmachines/pull/13)) proposes how to ingest library books into the Oracle, pending Aneesh's input on retrieval quality tradeoffs.

## 2026-05-25 · vgr
Added a direct-push inbox flow for submitting new writing without going through the web form or a fork/merge. Contributors add lines to `new_writing_inbox.md` in the repo root (`handle | type | url`) and push to main; a GitHub Actions workflow ingests the entries, clears the file, rebuilds the site, and deploys — same pipeline as the web form. Also populated the HANDLES KV with all contributor emails (several were missing due to the May 20 binding fix arriving after initial setup) and synced the Cloudflare Access allowlist to match.

## 2026-05-20 · vgr
Fixed a silent infrastructure breakage: the `HANDLES` KV binding had been dropped when Aneesh's Oracle commit introduced `wrangler.jsonc` on May 12, causing the contributors page, submit form, and admin UI to fail silently ever since. Fixed by adding the binding to `wrangler.jsonc` and manually writing the missing KV entry for Sean Stevenson. Added `ARCHITECTURE.md` as a full technical reference for the website stack (bindings, deployment, APIs, pipelines), and a proper `README.md` for the GitHub repo landing page.

## 2026-05-14 · vgr (2)
Added `rebuild.yml` GitHub Actions workflow — pushes to `devlog.md` or `blurbs.md` now auto-rebuild and deploy the site, no manual `build.py` or wrangler step needed. Added session wrap-up checklist to `CLAUDE.md` and a security policy (no credentials in tracked files) to `CONTRIBUTING.md`. Opened issue #10 proposing wiki generation pipeline and browsing layer options.

## 2026-05-14 · vgr
Promoted Aneesh's Oracle preview to `/oracle` — the stub is now the live RAG interface. `/notes` redirects to `/oracle`. Oracle is public (no auth gate). Nav updated to include Devlog. Also merged PR #9 (Oracle infrastructure): created R2 bucket `worldmachines-notes`, applied Pages R2+AI bindings, set up `CF_AI_TOKEN`/`CF_R2_TOKEN` GitHub secrets, ran first notes-ingest (743 notes embedded). Added two raw notes: Prime Radiant and Stigmergic-Verbose Cycle. Opened issue #10 proposing wiki generation pipeline.

## 2026-05-12 · aneesh
Working Oracle preview at `/notes`: a personal-notes Parquet on R2 with EmbeddingGemma-300M vectors per row, in-browser DuckDB-WASM does cosine-similarity retrieval, Gemma-4-26B answers via a Pages Function — single-voice Oracle output, no citations. `tools/notes-pipeline/` uv project builds the parquet (single- or multi-contributor mode). A new `notes-ingest` GitHub workflow rebuilds and uploads the parquet on every push to `raw-notes/`. ADR at `wiki/decisions/0001-notes-oracle-architecture.md`. Page is unlinked from site nav and not at `/oracle` — that stub stays until Venkat reviews.

## 2026-05-09 · aneesh
Added a "Project Chat" link to the site nav pointing to the Zulip server (`worldmachines.zulipchat.com`), so contributors can find the chat from any page.

## 2026-05-08 · vgr
Governance and tooling session. Reviewed and merged Kyle's repo restructure PR; resolved a ruleset conflict where the hard PR-gate was blocking the ingest bot, settling on soft governance (CODEOWNERS and `approval-policy` workflow active but advisory). Added this devlog page and a `devlog-check` workflow to flag non-trivial commits that skip the log.

## 2026-05-07 · kyle
Reorganized the repository for multi-person collaboration. Three zones now: `raw-notes/` for per-collaborator working notes, `wiki/` for the shared AI-organized knowledge layer, and `website/` for the public site. Added CODEOWNERS and an `approval-policy` workflow enforcing zone-specific review requirements (website PRs need Venkat; wiki PRs need any admin; raw-notes are self-owned).

## 2026-05-04 · vgr
Metadata backfill. Recovered publication dates for all 22 essays via trafilatura URL extraction, and first-publication years for 31 of 38 books via the Open Library API. Seven books still need manual correction — the API returned edition or translation dates rather than original publication years.

## 2026-05-04 · vgr
Site structure and contributor tooling. Split content into a blurb landing page, `/contributions` for member essays, and `/resources` for the curated reading list. Added self-service `/profile` editing, a `/theory` introduction page, and a comprehensive CSS overhaul. Batch-loaded all 60 articles (22 contributions, 38 resources/books).

## 2026-05-04 · vgr
Project launch. Stood up the full pipeline: Cloudflare Pages hosting at worldmachines.org, Access email-OTP gate for contributors, Pages Functions backed by KV for the handle registry, and GitHub Actions ingest (trafilatura text extraction → build.py HTML generation → Pages deploy).

