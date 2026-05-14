# ADR 0001 — Notes Oracle architecture: DuckDB-WASM + Parquet on R2 + Workers AI

**Status:** accepted
**Date:** 2026-05-12
**Authors:** aneesh
**Supersedes:** none

## Context

The site currently has an `oracle.html` stub that promises "an AI-powered interface for querying the World Machines corpus." We want to ship a working version, starting from one collaborator's personal notes (~750 markdown files in `/matiswiki/essays/Essays/`) as the seed corpus, and grow toward a multi-user system as more collaborators contribute.

We already shipped a local-only prototype on this branch:

- `tools/notes-pipeline/` — uv Python project; `notes_to_parquet.py` converts a directory of markdown notes into a single Parquet table with columns `path, slug, title, category, summary, tags[], last_updated, body, word_count, char_count, wiki_links[]`.
- `website/notes.html` — loads DuckDB-WASM in the browser, registers the Parquet as a virtual table, exposes a SQL playground.

This works for keyword/structured queries but cannot answer paraphrased questions ("what is liveness?") unless the user types the exact term. To act as the Oracle we need semantic retrieval and an LLM in the loop.

## Decision

Build the Oracle as a thin **retrieval-augmented chat layer over the existing Parquet**, hosted entirely on Cloudflare's free tier:

1. **Storage** — Parquet file on **Cloudflare R2** (10 GB + free egress). Bucket is private; served to the browser via a Pages Function proxy that supports HTTP range requests (DuckDB-WASM streams a few KB of footer + selective row groups, not the whole file).
2. **Embeddings** — `@cf/baai/bge-base-en-v1.5` via **Workers AI** (10k Neurons/day free). Generated once offline per note (or per chunk if the note is long) by the pipeline and stored as an additional `embedding float[768]` column in the same Parquet. No separate vector DB.
3. **Retrieval** — runs in the browser. The Pages Function `/api/embed` returns the embedding for the user's question; DuckDB-WASM then does `ORDER BY array_cosine_similarity(embedding, $q) DESC LIMIT k` against the local Parquet.
4. **Chat** — Pages Function `/api/chat` takes the question + top-k retrieved chunks and calls Workers AI (Llama 3.x family) for a streamed answer, with citations back to the source note slugs.
5. **Access** — the Oracle page is Access-gated like `/submit` and `/profile`, so personal notes are not publicly readable. The R2 bucket stays private; only the Pages Function reads from it.

## Why not Vectorize (yet)

Cloudflare Vectorize offers a native ANN index with a generous free tier and would be the obvious "production" choice. We are deliberately deferring it:

- **In-browser cosine similarity over a single Parquet comfortably handles up to ~10k–50k notes** with a 768-dim float embedding column (≈3 MB per 1k notes). At 750 notes today, scan cost is negligible.
- **One source of truth.** Embeddings live next to the text they describe; no separate index to keep in sync when notes change.
- **Faster to iterate.** Regenerating the corpus is a single `uv run` + R2 upload; no schema migrations.
- **Clean migration path.** If we cross the in-browser ANN ceiling, we move the `embedding` column out into Vectorize and switch retrieval to a Pages Function. The Parquet remains the system of record for text + metadata.

## Why not a per-user file layout yet

We discussed Hive partitioning (`user=alice/category=concepts/…`) vs. one Parquet per user. DuckDB-WASM cannot list HTTP filesystems, so Hive over R2 still requires an explicit URL manifest — partition-key pruning is the only real benefit, and it doesn't bite until a single user's file is very large. We are starting with a single `notes.parquet` for one user and will fan out to `notes-data/{user}.parquet` + a tiny `manifest.json` when a second collaborator joins.

## Architecture diagram

```
+--------------------+         +-------------------------+
| Browser            |         | Cloudflare Pages        |
|                    |  GET    |                         |
|  notes.html        | ------> | /api/notes-parquet      |
|  DuckDB-WASM       |         |   proxies R2 bucket     |
|                    |  POST   |                         |
|  fetch embedding   | ------> | /api/embed              |
|  for question      |         |   Workers AI (bge-base) |
|                    |         |                         |
|  in-browser ANN    |         |                         |
|  over Parquet      |         |                         |
|                    |  POST   |                         |
|  send top-k chunks | ------> | /api/chat               |
|                    |         |   Workers AI (Llama)    |
|                    | <-----  |   streams answer        |
+--------------------+         +-------------------------+
                                          |
                                          v
                                 +-----------------+
                                 | R2: notes-data  |
                                 |   notes.parquet |
                                 +-----------------+
```

## Pipeline shape

```
matiswiki/essays/Essays/        (markdown notes, local-only)
        |
        |  uv run notes_to_parquet.py
        v
website/notes-data/notes.parquet  (gitignored; includes embedding column)
        |
        |  wrangler r2 object put
        v
R2: worldmachines-notes/notes.parquet
```

The pipeline is a one-shot script for now. It runs whenever notes change; we can promote it to a GitHub Action later, but that requires the notes source to be reachable from CI (currently outside the repo).

## Open questions

- **Which chat model on Workers AI?** Start with `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (or the latest 70B available); fall back to `8b` if latency is bad.
- **Citation rendering.** Return the top-k chunks' `(title, slug)` in the function response so the frontend can render footnote-style citations.
- **Chunk size.** Some notes are 20k+ words (e.g. `Index`). v1: embed the whole note; v2: split into ~500-token chunks with overlap and store one row per chunk.
- **When to add per-user files.** Trigger: a second collaborator opts in.
- **Public-facing version.** Today the Oracle behind Access. If we later want a public Oracle, we publish a subset of notes (essays only, not personal) as a separate `public-notes.parquet`.

## Account ownership constraint

Cloudflare bindings (`env.NOTES`, `env.AI`) only resolve resources **in the same account as the Pages project**. The Pages project `worldmachines` lives in Venkat's Cloudflare account, therefore:

- The R2 bucket `worldmachines-notes` **must be created in Venkat's account**, not a contributor's personal account.
- Workers AI invocations from the deployed Pages Functions bill **Venkat's** account against the free tier (10k Neurons/day; see cost section below).
- The `CLOUDFLARE_ACCOUNT_ID` secret reused by `notes-ingest.yml` must be Venkat's, so the CI's parquet upload lands in the same account whose Pages project will read it.

A contributor's local `wrangler login` will be against their personal account; that is fine for local development (miniflare-simulated R2 + the contributor's own Workers AI free tier) but **does not** produce a production-deployable setup.

## Pre-merge setup checklist (Venkat / account owner)

Complete before approving the Oracle PR. All of this is one-time setup; nothing recurs.

### 1. Create two GitHub Actions secrets

Generate two scoped Cloudflare API tokens at <https://dash.cloudflare.com/profile/api-tokens>:

| Token name (in GitHub) | Cloudflare permissions | Used by |
|---|---|---|
| `CF_AI_TOKEN` | Account → **Workers AI : Read** + Account → **Account Settings : Read** | Python embedding step in CI |
| `CF_R2_TOKEN` | Account → **Workers R2 Storage : Edit** + Account → **Account Settings : Read** | wrangler upload step in CI |

For each token, on the configuration screen: include "All accounts" (or scope to the one specific Cloudflare account that owns `worldmachines.org`), leave Client IP filtering blank, no TTL (or 6-month TTL for rotation hygiene).

Add to GitHub: repo Settings → Secrets and variables → Actions → New repository secret. Paste the token value once (it won't be shown again).

Kept as two narrow tokens rather than one combined token to limit blast radius on leak. Do not give either token Pages:Edit; that scope remains on the existing `CLOUDFLARE_API_TOKEN` used by `ingest.yml`. See [[project-wrangler-env]] in agent memory for why narrow scoping matters.

The third secret, `CLOUDFLARE_ACCOUNT_ID`, already exists and is reused.

### 2. Create the R2 bucket in the project's account

Once, using a token with R2: Edit permissions on Venkat's account (the `CF_R2_TOKEN` works):

```bash
CLOUDFLARE_API_TOKEN=<CF_R2_TOKEN> CLOUDFLARE_ACCOUNT_ID=<venkat's> \
  npx wrangler@4 r2 bucket create worldmachines-notes
```

The bucket is **private**. The Pages Function `/api/notes-parquet` proxies reads from it; the browser never reaches R2 directly.

### 3. Attach bindings to the Pages project

Two paths — either works:

- **Easier (dashboard):** Pages dashboard → `worldmachines` → Settings → Bindings → add **R2 (`NOTES` → `worldmachines-notes`)** and **AI (`AI`)**. Persists indefinitely.
- **Or (wrangler config):** Pages dashboard → Build configuration → enable "Use wrangler.toml as deployment source". The `website/wrangler.jsonc` committed in this PR declares both bindings; deploys will pick them up automatically.

### 4. (Optional) Confirm Workers Paid plan status

The free 10,000 Neurons/day cap is sufficient for expected traffic (see cost section). Going *over* the free tier requires the Workers **Paid plan** ($5/month base for Workers). If the account is on the free Workers plan today, going over caps just fails the request rather than billing — there's no surprise bill exposure.

## Expected costs (Venkat's account)

Both Gemma-family models, but priced differently:

| Model | Role | $/M input | $/M output | Neurons/M tokens |
|---|---|---|---|---|
| `@cf/google/embeddinggemma-300m` | Notes ingest + per-question embedding | not on public table yet* | n/a | ~6,058 (est.) |
| `@cf/google/gemma-4-26b-a4b-it` | Oracle chat | $0.100 | $0.300 | 9,091 in / 27,273 out |

\* EmbeddingGemma's per-token cost isn't yet on the Workers AI pricing page (recent addition). Estimate uses `@cf/baai/bge-base-en-v1.5` ($0.067/M, 6,058 Neurons/M) as a same-dimension, comparable-size stand-in. EmbeddingGemma is ~3× the parameter count so the true rate may be up to 3× higher.

**Account-wide free tier:** 10,000 Neurons/day. Over the cap: $0.011 per 1,000 Neurons (requires Workers Paid plan).

### Notes ingest, per CI run

Today's corpus: 742 notes × ~1,550 tokens (title + summary + truncated body) ≈ **1.15M input tokens / run**.

| | Per run |
|---|---|
| Neurons consumed | ~7,000 (≈70% of one day's free 10k) |
| Cost if over free tier | ~$0.08 (worst-case 3× = $0.24) |

Scales linearly with corpus size. At 5,000 total notes: ~50k Neurons/run, ~$0.40 worst-case.

Triggers: every push to `main` touching `raw-notes/**`, `tools/notes-pipeline/**`, or `.github/workflows/notes-ingest.yml`; plus manual `workflow_dispatch`. Expect 1–5 runs/month in normal use.

### Chat, per user question

Typical: ~700 input tokens (system prompt + 6 retrieved chunks + question) + ~500 output tokens.

| Metric | Per question |
|---|---|
| Neurons | ~20 (6 in + 14 out) |
| Cost over free tier | $0.00022 |
| Free questions/day | ~500 |

| Question volume | Estimated monthly cost |
|---|---|
| 10/day | $0 (free tier) |
| 100/day | $0 (free tier) |
| 500/day | $0 (at the cap) |
| 1,000/day | ~$3.30 |
| 5,000/day | ~$26 |

### Bottom line

For realistic early traffic (handful of contributors, ≤ daily ingest, ≤ 100 questions/day across all users): **$0–$3/month**. To exceed $10/month would require sustained 1,500+ questions/day for a full month.

Adjacent line items, all effectively free at our scale:

- **R2 storage** — 10 GB free; our parquet is ~4 MB.
- **R2 operations** — millions/month free; we're at hundreds.
- **Pages Functions invocations** — 100k/day free.
- **GitHub Actions minutes** — generous on public repos; one ingest run is ~3 minutes.

## Merge order recommendation

Two PRs, in this sequence:

1. **`copy-matiswiki-essays-to-raw-notes` PR** (raw-notes only, no review needed per CONTRIBUTING.md): adds ~740 essays under `raw-notes/aneesh/`. Spends zero Neurons because the ingest workflow doesn't exist on `main` yet.
2. **This Oracle PR**: adds infra, simplified UI, the workflow. When it merges, the workflow's path filter matches the new `tools/notes-pipeline/**` files, so CI runs *once* and ingests the (now-populated-from-step-1) `raw-notes/`. The first run produces the correct full parquet without any manual intervention.

## Acceptance

This ADR moved from "proposed" to "accepted" on 2026-05-12 after a `wrangler pages dev` session demonstrated the full retrieval-augmented chat flow end-to-end: parquet served from local R2 via `/api/notes-parquet`, question embedded via `/api/embed`, top-k retrieved in-browser, answer streamed from `/api/chat`.

## Voice decision (post-acceptance)

Original draft cited retrieved notes inline (`[1] [2]`). The accepted version drops citations entirely — the Oracle speaks in a single project voice, weaving the wiki's threads into a unified reading rather than attributing claims to specific notes or contributors. Reasoning: as the corpus grows to many contributors, citation-by-note-number would become noisy and would frame the Oracle as a literature-review tool rather than a synthesis tool. The retrieved chunks remain in the prompt as background knowledge; the model is instructed not to surface them as sources. A future revision may add an inspection panel for transparency.
