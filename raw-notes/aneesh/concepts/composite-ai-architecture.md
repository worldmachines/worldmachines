---
summary: "The thesis that combining domain experts, large language models, and knowledge graphs creates a system capable of accelerating knowledge-intensive fields by externalizing expertise and making it traversable."
tags: [ai-architecture, knowledge-graphs, llm, expertise, healthcare-ai, explainability]
last_updated: 2026-04-09
---

# Composite AI Architecture (Experts + LLM + KG)

## The Thesis

Sathe (see [[Dancing on the Shoulders of Giants]], [[FHIR Knowledge Graphs Healthcare]]) argues that the current dominant approach to AI — "throwing mountains of data into hot cauldrons of compute" — has fundamental structural limitations: LLMs hallucinate, lack explainability, and cannot be cheaply or reliably updated with new domain knowledge. The alternative is not to fix LLMs but to pair them with complementary systems:

```
Domain Expert  +  Large Language Model  +  Knowledge Graph
(taste / judgment) (natural language interface) (grounded, auditable facts)
```

Each component addresses the weaknesses of the others:
- **KG** provides grounded, auditable, causally structured knowledge. Does not hallucinate. Cheap to query. Hard to interact with.
- **LLM** provides natural language interface and flexible reasoning. Easy to interact with. Hallucinates. Expensive.
- **Expert** provides taste, judgment, and the ability to override both when something seems wrong.

## Why It's a "Composite Material"

The metaphor is deliberate: a composite material has properties none of its components have alone. The Experts+LLM+KG composite can:
- Answer complex relational questions in natural language (impossible with KG alone)
- Ground answers in verified, auditable data (impossible with LLM alone)
- Override outputs when they conflict with clinical judgment (impossible with either alone)

## The Giant's Causeway Metaphor

Newton's "standing on the shoulders of giants" describes vertical accumulation — climbing knowledge slowly through education and experience. The composite architecture creates what Sathe calls "the Giant's Causeway of Intelligence" — a horizontal crossing, walking across externalized expertise rather than climbing it. The crossing is made possible by:
1. [[Cognitive Task Analysis]] — extracting tacit expert knowledge into KG-compatible form
2. [[Knowledge Graphs]] — encoding that knowledge as traversable structure
3. LLMs — providing natural language navigation across the graph

## Applications

- **[[Healthcare]]**: Integrating [[FHIR]] EHR data, clinical knowledge KGs, and LLM interface for diagnosis support, drug discovery, outcome prediction
- **Drug discovery**: Multi-domain disease complexity exceeds any single human mind's capacity; composite architecture manages the complexity
- **Knowledge diffusion**: Compressing generational knowledge transfer — applying each breakthrough without waiting a generation

## Economic Case

Retrieving an answer from a KG is 50x cheaper than generating it with an LLM. The composite architecture routes factual queries to the KG, using the LLM only for interaction and synthesis — dramatically reducing cost while improving reliability.

## Relationship to Wright's Law

This architecture is the proposed mechanism for applying [[Wright's Law]] dynamics to healthcare — creating the shared knowledge infrastructure that enables compounding efficiency gains.

## Related Concepts

- [[Knowledge Graphs]] — the grounding layer
- [[Retrieval-Augmented Generation]] — a simpler precursor architecture
- [[Explainable AI]] — what the architecture achieves
- [[Expertise]] — the human component the architecture supports
- [[Taste as Epistemic Capacity]] — what the human expert brings that the architecture cannot replace
- [[Wright's Law]] — the efficiency-compounding aspiration
- [[Cognitive Task Analysis]] — the knowledge extraction method
