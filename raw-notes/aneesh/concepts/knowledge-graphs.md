---
summary: "Data structures representing entities and their relationships as interconnected nodes and edges — powerful tools for managing complex information, but critically dependent on ontological scaffolding."
tags: [knowledge-graphs, ontologies, AI, semantic-web, data-infrastructure, knowledge-management]
last_updated: 2026-04-09
---

# Knowledge Graphs

A **knowledge graph** (KG) is a data structure that represents entities (nodes) and the relationships between them (edges), enabling machines to reason over complex, interconnected information. KGs have emerged as a primary tool for managing the structured knowledge that raw data and language models alone cannot provide.

## Why KGs Matter

In an era of data abundance and [[AI Slop]], the bottleneck is not data but *structured meaning*. KGs bridge the gap between raw information and actionable insight by making relationships explicit.

Key capabilities:
- **Semantic interoperability**: data from disparate sources can be integrated when grounded in shared vocabulary
- **Deductive reasoning**: inferring new knowledge from existing relationships
- **Machine learning support**: structured background knowledge for ML models, including explainable AI
- **Hypothesis generation**: in drug discovery, connecting genes, proteins, and diseases to identify targets

## The Ontology Dependency

A KG without a [[Domain Ontology]] is a collection of isolated data points. The ontology defines:
- What types of entities can exist (node types)
- What types of relationships can hold (edge types)
- Semantic constraints and definitions

This is the central argument of [[Domain Ontologies — Indispensable for Knowledge Graph Construction]].

## Example KGs

- **[[PrimeKG]]** — multimodal precision medicine KG
- **[[NP-KG]]** — pharmacokinetic natural product-drug interaction KG
- **[[ChEBI]]** — Chemical Entities of Biological Interest (foundational biomedical ontology/KG)

## Challenges

1. **Integration gap**: Most ontologies are abstract models not designed to hold data — requires (semi-)automated integration pipelines
2. **Semantic inconsistency**: Multiple competing ontologies in a domain create irreconcilable representations
3. **Maintenance**: KGs require ongoing labor to remain accurate and current
4. **Scale vs. depth**: Larger KGs capture more entities but may sacrifice semantic precision

## KGs as Bridges in the Knowledge Stack

The [[Universal Library in the River of Noise]] proposes KGs as "bridges between curated knowledge and generated text." In this framing:

```
Raw data → Ontology → Knowledge Graph → LLM grounding → Natural language
```

[[Domain Ontologies]] provide the left side of this bridge; [[LLMs]] provide the right. KGs are the connective tissue.

## Connection to Idea-Graphs

The [[Cloister Web]] essay anticipates "[[Idea-Graphs]] and knowledge structures" as LLM-consumable political artifacts — a non-technical instantiation of the KG concept applied to intellectual and political discourse.

## Related Concepts

- [[Domain Ontologies]] — the prerequisite scaffolding
- [[FAIR Principles]] — the data standards KGs should satisfy
- [[Universal Library]] — KGs as the latest technological attempt to realize the universal library ideal
- [[Idea-Graphs]] — the political/intellectual application of KG thinking

## KGs vs. Basic RAG in Healthcare

Sathe argues (see [[FHIR Knowledge Graphs Healthcare]], [[Dancing on the Shoulders of Giants]]) that standard [[Retrieval-Augmented Generation]] fails healthcare because medical knowledge is inherently relational — diseases link to treatments link to contraindications link to patient-specific histories. Basic RAG retrieves passages that *mention* relevant entities but cannot traverse the *relationships* between them. KG-grounded retrieval fixes this by operating over typed relational structure.

The cost argument: retrieving an answer from a KG is cited as **50x cheaper** than generating it with an LLM. KGs also eliminate [[Hallucination]] for factual queries — the answer is looked up, not generated.

The interactivity problem: KGs are hard to query without technical expertise. The [[Composite AI Architecture (Experts + LLM + KG)]] resolves this: LLM handles natural language interface, KG supplies grounded facts.

**[[FHIR]]** provides the EHR interoperability standard that feeds healthcare KGs. **[[PrimeKG]]** combines multiple KGs for multimodal clinical knowledge integration.

## Relationship to Expertise Structure

"Dancing on the Shoulders of Giants" draws an analogy between expert cognition and KG structure: experts store knowledge relationally, with context attached to both entities and relationships — exactly how KGs work. Externalizing expertise into a KG means the knowledge doesn't die with the expert or remain siloed in one institution, enabling [[Wright's Law]]-style compounding in fields that have historically resisted it.

## Sources

- [[Domain Ontologies — Knowledge Graph Construction]] (summary)
- [[Universal Library in the River of Noise]] (summary)
- [[FHIR Knowledge Graphs Healthcare]] (summary) — healthcare RAG + KG architecture
- [[Dancing on the Shoulders of Giants]] (summary) — KGs as crystallized expertise, 50x cost claim
