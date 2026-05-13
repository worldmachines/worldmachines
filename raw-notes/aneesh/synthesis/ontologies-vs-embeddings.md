---
summary: "Two approaches to the same aspiration — semantic structure without ambiguity — that are complementary rather than competing: explicit ontological declaration vs. statistical vector representation."
tags: [ontologies, LLMs, embeddings, semantic-web, knowledge-representation, synthesis]
last_updated: 2026-04-09
---

# Ontologies vs. Embeddings — Two Paths to Semantic Structure

Both [[Domain Ontologies]] and LLM embeddings represent attempts to solve the same problem: how do you give a machine a meaningful representation of concepts such that it can reason over them reliably?

They take structurally opposite approaches.

## The Shared Aspiration

Both are heirs to the [[Perfect Language]] dream — the Leibnizian ideal of a representational system where:
- Each concept has a unique, unambiguous location
- Relationships between concepts are explicit and computable
- Reasoning over the representation is reliable

[[Umberto Eco]] identified AI as a "revival under a different name" of this dream. He was gesturing at embeddings. But ontologies are the *other* revival — older, more conservative, more deliberate.

## The Approaches Contrasted

| Dimension | Domain Ontologies | LLM Embeddings |
|---|---|---|
| Nature | Explicit, declared | Implicit, statistical |
| Construction | Expert-built, labor-intensive | Learned from data |
| Coverage | Domain-scoped | Web-scale |
| Reliability | High within domain, brittle outside | Probabilistic, confident errors |
| Reasoning | Deductive (guaranteed valid) | Pattern-matching (plausible) |
| Ambiguity handling | Eliminated by design | Approximated by proximity |
| Interpretability | Fully legible | Opaque (black box) |
| Update cost | High (expert revision) | Low (retraining) |

## The Synthesis Needed

Neither is sufficient alone:
- Ontologies cannot scale to web-level data without enormous labor
- Embeddings hallucinate and cannot guarantee logical consistency

The literature cited in [[Domain Ontologies — Indispensable for Knowledge Graph Construction]] points toward a synthesis: **ontology-grounded KGs + LLM interfaces**. The ontology provides the logical backbone; the LLM provides the natural language interface and fills in the spaces between explicit nodes.

Gilbert et al. (2024) — "Augmented non-hallucinating large language models using ontologies and knowledge graphs in biomedicine" — is the direct technical instantiation of this synthesis.

## The Political Dimension

The [[Cloister Web]] essay introduces a third path: **[[Idea-Graphs]]** — explicit relational structures built for LLM consumption but designed for political-intellectual rather than scientific domains. Idea-graphs occupy the middle ground: more structured than plain text (like ontologies), more flexible than formal ontologies (because political concepts resist strict formalization).

## Essay Seed

This tension is potentially the core of a substantial essay: **the two revivals of the Perfect Language dream** — one explicit (ontological engineering), one statistical (deep learning) — are converging on a synthesis that neither camp fully anticipated. The future of knowledge infrastructure may be hybrid: ontologically structured cores with LLM-mediated peripheries.

## Related Pages

- [[Domain Ontologies]] — the explicit approach
- [[Perfect Language]] — the shared ancestor
- [[Knowledge Graphs]] — the synthesis infrastructure
- [[Cloister Web]] — political application
- [[Idea-Graphs]] — the political middle ground
- [[Universal Library]] — the macro-scale aspiration both serve
