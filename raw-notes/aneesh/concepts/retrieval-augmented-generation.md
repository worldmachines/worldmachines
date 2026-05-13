---
summary: "A technique for grounding language model outputs in retrieved external documents, improving factuality while preserving natural language generation — and its limitations in complex, relational domains like healthcare."
tags: [ai-architecture, llm, information-retrieval, healthcare-ai, rag]
last_updated: 2026-04-09
---

# Retrieval-Augmented Generation (RAG)

## Definition

RAG is an architecture where, before generating a response, a language model retrieves relevant passages from an external corpus and conditions its generation on them. This grounds the output in actual documents, improving factuality over pure generation from latent weights.

## Variants

- **Basic RAG**: Retrieve top-k documents by keyword or embedding similarity; insert into the LLM's context window; generate.
- **Advanced RAG**: Use structured retrieval over [[Knowledge Graphs]] rather than flat document stores; retrieve typed relationships rather than passages; enables multi-hop reasoning across linked entities.

## Limitations in Healthcare (Basic RAG)

Sathe identifies a fundamental mismatch between basic RAG and healthcare requirements (see [[FHIR Knowledge Graphs Healthcare]]):
- Healthcare knowledge is **relational**, not textual — the meaningful unit is a relationship between disease, treatment, contraindication, and patient history, not a paragraph about any of them in isolation.
- Basic RAG retrieves passages that *mention* relevant entities but cannot traverse the *relationships* between them.
- Result: retrieval is relevant but shallow; the model can say "metformin is used for diabetes" but cannot reason about the specific patient's comorbidities and what that implies for dosing.

## The Advanced RAG Solution

Advanced RAG operating over FHIR-structured [[Knowledge Graphs]] addresses these limitations:
- Retrieval traverses typed relationships (not keyword co-occurrence)
- Responses are grounded in verified, structured medical knowledge
- Patient-specific information integrates with population-level evidence
- The result is "enriched AI responses with verified medical knowledge and patient-specific information"

## Related Concepts

- [[Knowledge Graphs]] — the structured substrate that advanced RAG operates over
- [[FHIR]] — the interoperability standard enabling healthcare KG construction
- [[Hallucination]] — the failure mode RAG partially mitigates
- [[Explainable AI]] — advanced RAG improves explainability but doesn't fully achieve it
- [[Composite AI Architecture (Experts + LLM + KG)]] — RAG as one component
