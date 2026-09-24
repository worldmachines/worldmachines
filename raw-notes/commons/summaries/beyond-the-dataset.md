---
summary: "Argues that data science must rigorously trace both how data is measured and how comparisons are drawn, or all downstream analysis is untrustworthy."
tags: [data-science, epistemology, measurement, causality, statistics]
last_updated: 2026-04-09
---

# Beyond the Dataset

**Source**: Aneesh Sathe, *Beyond the Dataset* (2025-07-11) — https://aneeshsathe.com/beyond-the-dataset/

## Central Argument

A data scientist must understand the full data generation process before doing any analysis. This process rests on two load-bearing pillars: **how we measure** (the trip from reality to raw numbers) and **how we compare** (the causal and statistical logic that lets numbers answer questions). A crack in either pillar invalidates everything built on top — plots, significance tests, AI predictions alike.

## Key Frameworks

### The Two Pillars of Trustworthy Analysis
1. **How we measure** — instrument design, sensor calibration, feature extraction, label quality. Analogized to a misaligned microscope: no post-processing can recover a photon that never hit the sensor. See [[Point Spread Function and Measurement Fidelity]].
2. **How we compare** — randomization, controls, confounders, causal structure. Sound comparisons must be designed before data is collected, not retrofitted afterward.

### Data-Centric AI (Andrew Ng)
Tightening labels, fixing sensor drift, and writing clear provenance notes often outperform switching to fancier models. The key insight: improving *data quality* beats improving *model architecture* when the data generation process is poorly understood. See [[Data-Centric AI]].

### Breiman's Two Cultures
[[Leo Breiman]] (2001) warned that many analysts chase algorithmic accuracy while skipping the question of how data were generated. Today's auto-chart and one-click-model tooling intensifies this temptation. See [[Breiman's Two Cultures]].

## Key Examples

- **Fluorescence imaging**: Point-spread functions and photon noise mean a cell appearing "twice as bright" may be an artifact of instrument settings.
- **Fertilizer trial on sunny plots**: Confounding by sunlight invalidates any causal inference about the fertilizer.
- **COVID-19 regional death rates**: Early claims of miracle policies collapsed when confounders (age distribution, testing access, hospital load) were controlled for.

## Structural / Organizational Argument

In startups and scientific settings alike, the necessary expertise must be split across people. The data scientist's job is to collect information *horizontally* — bridging domain science, instrumentation knowledge, and statistical reasoning. Leadership must enable this culture or accept uninformed risk.

## What the Author Doesn't Address

- How to institutionalize data provenance tracking in organizations with high turnover.
- The tension between data-centric AI (clean labels) and the practical reality of scarce labeling budgets.
- When "good enough" data quality is genuinely sufficient vs. when the pillar is cracking unnoticed.

## Cross-References

- [[Data Generation Process]]
- [[Measurement and Epistemology]]
- [[Causal Inference]]
- [[Confounding Variables]]
- [[Data-Centric AI]]
- [[Leo Breiman]]
- [[Andrew Ng]]
- [[Breiman's Two Cultures]]
