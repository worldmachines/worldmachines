---
summary: "Andrew Ng's framework arguing that improving data quality (labels, provenance, collection consistency) typically yields more performance gains than improving model architecture."
tags: [data-science, machine-learning, AI, Andrew-Ng, measurement]
last_updated: 2026-04-09
---

# Data-Centric AI

**Data-Centric AI** is a framework advanced by [[Andrew Ng]] in contrast to the dominant model-centric paradigm in machine learning.

## Core Claim

Given a fixed model architecture, improving *data quality* — label consistency, sensor calibration, provenance documentation — often yields more performance gain than switching to a more powerful model. The bottleneck is the [[Data Generation Process]], not the algorithm.

## Practical Prescriptions

1. **Tighten labels** — reduce labeling inconsistency across annotators; write clear annotation guidelines
2. **Fix sensor drift** — monitor and correct for instrument drift over time rather than treating it as noise
3. **Write provenance notes** — document where data came from, how it was collected, and what assumptions apply
4. **Audit data distributions** — identify systematic biases in what was and wasn't collected

## Relationship to the Two Pillars

Data-centric AI focuses on the first pillar of trustworthy analysis ([[Data Generation Process#Measurement]]): how we measure. It says: the quality of your measurement process is the binding constraint. See [[beyond-the-dataset|Beyond the Dataset]].

## Limits / Critique

- Does not address the *second pillar*: even perfect data cannot rescue a poorly designed experiment (confounding variables, wrong randomization).
- May be less applicable when data collection is cheap and unlimited (internet-scale data for LLMs).
- "Data quality" is context-dependent — what counts as a label error depends on the task.

## Cross-References

- [[Data Generation Process]]
- [[Andrew Ng]]
- [[Measurement and Epistemology]]
- [[Breiman's Two Cultures]]

## Sources
- [[beyond-the-dataset|Beyond the Dataset]] (Aneesh Sathe, 2025)
