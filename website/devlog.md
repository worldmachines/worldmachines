<!--
  Prepend new entries at the top. Format:  ## YYYY-MM-DD · handle
  Keep entries to 1–3 sentences: what changed and why it matters for the project.
  For trivial commits (typos, config tweaks), add [trivial] to the commit message
  instead of writing an entry here.
-->

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
