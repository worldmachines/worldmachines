<!--
  Prepend new entries at the top. Format:  ## YYYY-MM-DD · handle
  Keep entries to 1–3 sentences: what changed and why it matters for the project.
  For trivial commits (typos, config tweaks), add [trivial] to the commit message
  instead of writing an entry here.
-->

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
