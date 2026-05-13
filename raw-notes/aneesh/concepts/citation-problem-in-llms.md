---
summary: "The absence of verifiable source attribution in LLM outputs — a structural accountability gap that makes it impossible for users to audit, verify, or calibrate trust in AI-generated information."
tags: [llm, epistemics, accountability, transparency, citation]
last_updated: 2026-04-09
---

# Citation Problem in LLMs

## The Problem

When a language model answers a question, it draws on patterns from training data — but the specific sources that informed any particular output are not accessible. The xkcd "citation needed" joke, originally aimed at Wikipedia editors and politicians, has become a serious epistemic concern: unlike Wikipedia (which demands citations) or search engines (which link to sources), LLMs provide no trail.

The specific failure modes:
1. **No provenance** — users cannot identify what source an answer derived from
2. **No confidence signal** — LLMs state hallucinations with the same fluency as facts
3. **No auditability** — there is no mechanism to check whether a cited relationship is accurately reproduced

## Why It Matters

Sathe frames this as the difference between the xkcd joke being funny and being dangerous (see [[My Grandfather Had Lore]]). In low-stakes contexts, a confident wrong answer is annoying. In [[Mission-Critical AI]] domains — healthcare, legal, defense — a confident wrong answer with no traceable source is a liability.

The citation problem also undermines the case for AI as an advisor (see [[AI as Tool vs. Advisor]]): advisors are expected to ground their recommendations in evidence, and to be accountable when recommendations fail.

## Attempts at Resolution

- **[[Perplexity AI]]**: Grafts citations onto LLM outputs. Sathe acknowledges the effort but doubts it solves the underlying trust problem — the citation is post-hoc, not part of the generation mechanism.
- **[[Retrieval-Augmented Generation]]**: Inserts retrieved passages into the generation context. Reduces hallucination, makes sources more visible, but still allows the model to misrepresent what it retrieved.
- **[[Knowledge Graphs]]**: Bypass generation entirely for factual queries — the answer comes from structured data with a clear provenance path.

## Related Concepts

- [[Hallucination]] — the content failure that citations would mitigate
- [[Explainable AI]] — the broader principle
- [[Lore vs. Search vs. LLM]] — historical context for why this is a regression
