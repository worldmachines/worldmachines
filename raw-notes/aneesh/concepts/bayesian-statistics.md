---
summary: "A statistical framework in which probability represents degrees of belief updated by evidence, enabling explicit modeling of uncertainty, small-sample inference, and transparent communication of causal assumptions through the data generating process."
tags: [statistics, bayesian, epistemology, causal-inference, scientific-method, data-generating-process]
last_updated: 2026-04-09
---

# Bayesian Statistics

A framework for statistical reasoning in which probability represents a degree of belief about a hypothesis, updated continuously as new evidence arrives. Contrasts with [[Frequentist Statistics]], where probability is the long-run frequency of events and inference proceeds via hypothesis testing.

## Core Concepts

### Posterior Probability
The updated belief after observing data: P(hypothesis | data). Combines the prior belief with the likelihood of the observed data given the hypothesis.

### Prior
Beliefs about a parameter before observing data. In practice, priors encode domain knowledge or uncertainty. A major critique (and a major strength) of Bayesian inference: priors must be explicitly stated, making assumptions transparent and open to critique.

### Data Generating Process (DGP)
The causal mechanism by which observations come to exist. Bayesian modeling requires you to specify a DGP — typically expressed as a [[DAG (Directed Acyclic Graph)]] — and test whether your model generates data consistent with what you actually observe.

### No Minimum Sample Size
Unlike frequentist tests (t-tests recommended for n≥30), Bayesian methods can model any sample size. Small samples produce wider, more uncertain posteriors — but this uncertainty is *shown* rather than hidden. See [[My Road to Bayesian Stats]].

## Practical Advantages for Frontier Science

As [[Aneesh Sathe]] argues from biology:
- Can accept *and* reject both null and alternative hypotheses
- Can communicate degrees of uncertainty as posterior probabilities
- Makes no assumptions about normality or equal variance
- Outliers and unusual distributions are incorporated rather than discarded

## Epistemological Character

Bayesian inference is inherently *transparent*: to run a Bayesian analysis, you must make your causal model explicit, which means others can identify and correct mistakes. This is contrasted with frequentist analysis, where assumptions are hidden inside the statistical procedure.

[[Richard McElreath]]: *"There is no method for making causal models other than science. There is no method to science other than honest anarchy."*

## Cross-References

- [[Frequentist Statistics]] — the contrasted paradigm
- [[DAG (Directed Acyclic Graph)]] — the tool for representing the DGP
- [[Data Generating Process]] — the concept that grounds Bayesian modeling
- [[Causal Inference]] — the ultimate goal that Bayesian modeling enables
- [[Transparency in Scientific Method]] — the meta-value
- [[Richard McElreath]] — intellectual anchor for the causal turn in Bayesian practice
- Source: [[My Road to Bayesian Stats]]
