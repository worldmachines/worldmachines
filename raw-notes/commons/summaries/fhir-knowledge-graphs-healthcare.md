---
summary: "Sathe argues that standard RAG fails healthcare's complexity and proposes pairing FHIR-structured knowledge graphs with advanced RAG and AI agents to produce explainable, context-aware clinical AI."
tags: [healthcare-ai, rag, fhir, knowledge-graphs, ai-agents, explainability]
last_updated: 2026-04-09
---

# Reimagining AI in Healthcare: Beyond Basic RAG with FHIR, Knowledge Graphs, and AI Agents

**Source**: [aneeshsathe.com, 2024-05-03](https://aneeshsathe.com/reimagining-ai-in-healthcare-beyond-basic-rag-with-fhir-knowledge-graphs-and-ai-agents/)
**Author**: [[Aneesh Sathe]]

## Central Argument

Standard RAG — pulling from flat document stores — is insufficient for healthcare because medical knowledge is inherently relational: diseases link to treatments link to patient histories link to contraindications. FHIR provides a standard schema for structuring EHR data; knowledge graphs make those relationships machine-traversable; advanced RAG techniques operating over KG-structured data enable AI agents that can reason about individual patients in context rather than generating plausible-sounding generalizations.

## Key Claims

1. **Healthcare data is relational, not textual** — the core failing of basic RAG is treating medical knowledge as retrievable prose rather than as a network of typed relationships.
2. **FHIR as the interoperability layer** — Fast Healthcare Interoperability Resources standardizes EHR data formats, enabling data to move across systems. When mapped to a knowledge graph, it becomes queryable by AI in structurally meaningful ways.
3. **Advanced RAG over KGs** — "Advanced RAG techniques utilize detailed knowledge graphs covering diseases, treatments, and patient histories." The KG enriches the retrieval step with verified relational context before the LLM generates a response.
4. **AI agents as the delivery mechanism** — agents that combine RAG and KG can improve diagnosis accuracy, predict patient outcomes, and optimize treatment plans through aggregated and individualized medical knowledge.
5. **Challenges** — data privacy, computational cost, and the ongoing maintenance burden of keeping KGs current are identified as the primary barriers to deployment.

## Connections

- See [[Retrieval-Augmented Generation]] — the baseline technique and its limitations
- See [[FHIR]] — the EHR interoperability standard
- See [[Knowledge Graphs]] — the structural alternative to flat retrieval
- See [[AI Agents in Healthcare]] — the deployment architecture
- See [[Mayo Clinic]] — cited as a leading institution treating KGs as the path forward
- See [[Explainable AI]] — KGs make AI auditable, connecting to Sathe's broader epistemics
- Synthesis: [[Composite AI Architecture (Experts + LLM + KG)]] — the thesis elaborated more fully in [[Dancing on the Shoulders of Giants]]

## What's Missing

- No discussion of which FHIR resources map most naturally to KG structures
- Does not address the cold-start problem: knowledge graphs require expert curation before they become useful
- No case study or empirical benchmark — the claims are architecturally plausible but not evidenced here
