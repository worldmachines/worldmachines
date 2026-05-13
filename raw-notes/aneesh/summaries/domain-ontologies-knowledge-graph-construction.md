---
summary: "Aneesh Sathe's argument that domain ontologies are not merely useful but essential scaffolding for knowledge graph construction, with applications across biomedical, cultural, and AI domains."
tags: [ontologies, knowledge-graphs, AI, FAIR-data, biomedical-informatics, semantic-web, interoperability]
last_updated: 2026-04-09
---

# Domain Ontologies: Indispensable for Knowledge Graph Construction

**Source**: Aneesh Sathe, *Domain Ontologies: Indispensable for Knowledge Graph Construction* (2025-01-15)
**URL**: https://aneeshsathe.com/domain-ontologies-indispensable-for-knowledge-graph-construction/

## Central Argument

In an era of data abundance and increasing [[AI Slop]], [[Knowledge Graphs]] (KGs) are a powerful tool for deriving structured insights — but their value is entirely dependent on underlying [[Domain Ontologies]]. Ontologies are not optional refinements; they are the blueprint that makes a KG semantically coherent and interoperable rather than a collection of isolated data points.

## Key Claims

1. **Ontologies as blueprints**: They define the types of nodes (entities) and edges (relationships) in a KG. Without them, a KG cannot be semantically interoperable across sources.
2. **Data consistency and interoperability**: Across clinical trials, patient records, and publications, terms like "cancer" or "hypertension" mean different things without shared ontological grounding. [[FAIR Principles]] (Findable, Accessible, Interoperable, Reusable) require ontological anchoring.
3. **AI reasoning support**: Ontologies enable both deductive inference (deriving new knowledge) and structured background knowledge for machine learning — critical for explainable AI in high-stakes domains like medicine.
4. **Drug discovery example**: A biomedical KG grounded in ontology can identify drug targets by connecting genes, proteins, and diseases through clearly defined relationships.
5. **Challenges**:
   - Most ontologies are abstract models not designed to directly contain data — integration requires semi-automated pipelines
   - Multiple ontologies within a domain create semantic inconsistencies and "irreconcilability"
   - Future direction: ontologies designed explicitly for instantiation, with data stored directly in graph databases

## Exemplary Ontologies/KGs Cited

- **[[ChEBI]]** (Chemical Entities of Biological Interest) — biomedical domain standard
- **[[PrimeKG]]** — multimodal precision medicine KG
- **[[NP-KG]]** — pharmacokinetic natural product-drug interaction KG

## Intellectual Lineage

- Noy & McGuinness (2001) — "Ontology Development 101": foundational practical guide
- Al-Moslmi et al. (2021) — KG construction approaches survey
- Gilbert et al. (2024) — augmented non-hallucinating LLMs using ontologies/KGs in biomedicine
- Kilicoglu et al. (2024) — survey on biomedical KGs

## What the Essay Doesn't Address

- The political/institutional labor required to maintain ontologies over time (who funds and governs them?)
- The tension between domain-specific ontologies and the dream of a [[Universal Ontology]]
- How ontologies interact with the noisier, less structured web-scale data that LLMs are trained on

## Cross-Source Resonances

- Directly follows [[Universal Library in the River of Noise]]: KGs are proposed there as "bridges between curated knowledge and generated text" — this essay argues that bridge requires an ontological foundation
- Connects to [[Cloister Web]] on LLM latent space: if LLM embeddings approximate a [[Perfect Language]], ontologies are the explicit, legible version of the same aspiration
- See synthesis: [[Ontologies vs. Embeddings — Two Paths to Semantic Structure]]
