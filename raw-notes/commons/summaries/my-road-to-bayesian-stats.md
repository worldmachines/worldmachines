---
summary: "Aneesh Sathe recounts his conversion from frequentist to Bayesian statistics, driven by the inadequacy of p-values for small-sample biological experiments and the need for transparency about causal assumptions."
tags: [bayesian-statistics, frequentist-statistics, causality, scientific-method, DAGs, epistemology]
last_updated: 2026-04-09
---

# My Road to Bayesian Stats

**Source**: [aneeshsathe.com, 2025-07-22](https://aneeshsathe.com/my-road-to-bayesian-stats/)
**Author**: [[Aneesh Sathe]]
**Key Reference**: [[Richard McElreath]], quoted on causal models and scientific honesty

## Central Argument

Frequentist statistics — p-values, significance stars, the t-test — systematically fails biologists working at the frontier because it (a) requires minimum sample sizes biological experiments rarely meet, (b) cannot affirm the null hypothesis or communicate degrees of uncertainty, and (c) hides its own assumptions. [[Bayesian Statistics]] remedies all three failings while requiring more explicit reasoning about the [[Data Generating Process]] (DGP). The transparency cost is also the epistemic benefit.

## Key Claims

1. **P-values are asymmetric**: a low p-value says "unlikely the null is true" but cannot confirm the alternative is true, and cannot affirm that two groups have no difference. This is a fundamental logical limitation, not a statistical technicality.
2. **No minimum sample size**: Bayesian methods build a model from any number of observations and sample from it; small sample sizes produce weaker fits, but this is made *transparent* rather than silently inflating false confidence.
3. **Assumptions are made explicit**: frequentist methods assume normality and equal variance — biological data often violates both — but these assumptions are magicked away by the software. Bayesian models force you to state your assumptions in the form of a [[DAG]] (directed acyclic graph).
4. **[[DAGs]] as scientific infrastructure**: even outside Bayesian analysis, DAGs force explicit causal thinking. They are representations of the DGP — what causes what. Testing model fit against observed data validates the DGP hypothesis.
5. **Transparency enables correction**: if your causal model is wrong and explicitly stated, others can correct it. If it's hidden, correction is impossible.
6. **Bayesian stats can accept/reject both null and alternative hypotheses**: unlike frequentist stats, it can also communicate uncertainty as a posterior probability ("we are x% sure").

## Intellectual Lineage

- **[[Richard McElreath]]** — *Statistical Rethinking*: quoted on the inseparability of causal modeling from science itself; "honest anarchy" as the method of science
- **[[Data Generating Process]]** — the concept that statistical models must represent *how* observations come to exist
- **[[Frequentist Statistics]]** — the dominant paradigm being critiqued
- **[[Bayesian Statistics]]** — the proposed alternative

## Key Quotations

> "There is no method for making causal models other than science. There is no method to science other than honest anarchy."
> — Richard McElreath

## What's Missing

- No mention of computational costs of Bayesian inference (MCMC, Stan, PyMC) which are real barriers to adoption
- Doesn't engage with Bayesian critics — e.g., concerns about prior selection introducing bias
- The essay is personal/narrative; doesn't engage the reproducibility crisis literature, where frequentism's failures are most documented
- No discussion of how to communicate Bayesian outputs to non-statistician stakeholders

## Cross-References

- [[Bayesian Statistics]] — central concept
- [[Frequentist Statistics]] — the contrasted paradigm
- [[DAG (Directed Acyclic Graph)]] — key tool in Bayesian modeling
- [[Data Generating Process]] — core concept enabling transparent modeling
- [[Richard McElreath]] — intellectual anchor
- [[Causal Inference]] — the ultimate goal driving the Bayesian turn
- [[Transparency in Scientific Method]] — the meta-value the essay argues for
- Synthesis: [[Transparency as Epistemic Virtue]] — connecting to broader themes in explainable AI and open science
