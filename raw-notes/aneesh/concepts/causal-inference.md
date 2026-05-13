---
summary: "The formal and informal methods for moving from correlation to causation — requiring understanding of experimental design, confounders, and the data generation process before statistical analysis begins."
tags: [statistics, data-science, causality, methodology, epistemology]
last_updated: 2026-04-09
---

# Causal Inference

**Causal inference** is the discipline of drawing valid causal conclusions from data — moving from "X and Y are correlated" to "X causes Y." It requires understanding the [[Data Generation Process]] before statistical analysis, not as a post-hoc correction.

## The Core Problem

Correlation does not imply causation. The gap between the two is filled by:
1. **Experimental design**: randomization that breaks the correlation between treatment and [[Confounding Variables|confounders]]
2. **Causal modeling**: explicit representation of the causal structure (via DAGs or structural equations)
3. **Domain knowledge**: knowing which variables precede others, which are plausible causes

This information is not in the data. It must come from understanding the science of the experiment.

## Key Methods

| Method | When to Use | Key Assumption |
|---|---|---|
| **RCT** | Can randomize treatment | Randomization breaks all confounding |
| **Instrumental Variables** | Have an instrument (affects treatment, not outcome) | Instrument is valid |
| **Difference-in-Differences** | Have pre/post data for treated and control | Parallel trends |
| **Regression Discontinuity** | Treatment assignment has a cutoff | Continuity near cutoff |
| **DAG-based adjustment** | Know the causal structure | DAG is correctly specified |

## Sathe's Fertilizer Example

Testing a fertilizer only on sunny plots is a causal inference failure: the experimental design does not control for sunlight, so the estimate of fertilizer effectiveness is confounded. This failure cannot be corrected statistically — it is baked into the [[Data Generation Process]].

## COVID-19 Case

Early regional death-rate comparisons were causal inference failures: policies were correlated with outcomes, but age distribution, testing access, and hospital load were confounders. Later studies that controlled for these confounders found the apparent policy miracles vanished. See [[beyond-the-dataset|Beyond the Dataset]].

## Relationship to Breiman

[[Leo Breiman]]'s [[Breiman's Two Cultures|Two Cultures]] critique is partly a causal inference critique: the algorithmic modeling culture optimizes predictive accuracy on data without asking whether the causal structure is identified. A predictive model can be accurate for the wrong reasons.

## Cross-References

- [[Data Generation Process]]
- [[Confounding Variables]]
- [[Breiman's Two Cultures]]
- [[Data-Centric AI]]

## Sources
- [[beyond-the-dataset|Beyond the Dataset]] (Aneesh Sathe, 2025)
