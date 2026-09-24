---
summary: "An AI-powered search and answer engine that attempts to restore citations to LLM-generated responses — cited by Sathe as the most credible attempt to address the citation problem in LLMs, though with skepticism about whether it solves the underlying trust issue."
tags: [search, llm, citations, ai-products, information-access]
last_updated: 2026-04-09
---

# Perplexity AI

AI-powered search engine that combines large language model generation with real-time web retrieval, presenting cited sources alongside AI-generated answers. Founded 2022.

## Relevance to the Citation Problem

Sathe (see [[My Grandfather Had Lore]]) names Perplexity as the most significant attempt to address the [[Citation Problem in LLMs]]: "I understand that tools like Perplexity are trying to bring back the citation, and I hope they do a good job."

The implicit acknowledgment is significant — an AI practitioner who is deeply skeptical of LLM reliability is tracking citation-backed generation as the most promising mitigation. The skepticism is also notable: "as long as LLM and similar generative technologies are at the core, trust will remain an issue."

## The Architectural Critique

The concern is that Perplexity grafts citations onto LLM outputs post-hoc rather than deriving answers from structured, grounded retrieval. The citation shows *where* the model looked; it does not guarantee the answer accurately represents what it found. This is a softer version of the [[Composite AI Architecture (Experts + LLM + KG)]] argument: to get genuine epistemic grounding, you need structured data retrieval ([[Knowledge Graphs]], [[FHIR]]), not just citation metadata.

## Related Concepts

- [[Citation Problem in LLMs]] — the specific problem Perplexity addresses
- [[Degradation of Search]] — the market gap Perplexity occupies
- [[Lore vs. Search vs. LLM]] — Perplexity as a hybrid attempting to recover search-era citation norms
- [[Explainable AI]] — the normative standard Perplexity partially meets
