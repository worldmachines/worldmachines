---
summary: "A diagram of nodes and directed edges with no cycles, used in causal inference and Bayesian statistics to represent the data generating process — which variables cause which others."
tags: [DAGs, causal-inference, bayesian-statistics, data-generating-process, scientific-method]
last_updated: 2026-04-09
---

# DAG (Directed Acyclic Graph)

A graphical representation of causal relationships: nodes represent variables; directed edges (arrows) represent hypothesized causal influence; the "acyclic" constraint means no variable can be its own cause through a chain of effects.

## Role in Bayesian Statistics

In Bayesian modeling, the DAG is the formalization of the **[[Data Generating Process]]**: a hypothesis about *how the data came to exist*. Building a Bayesian model requires constructing a DAG, which forces the analyst to:

1. State which variables they believe are causally relevant
2. State the direction of causal influence
3. State which variables are observed and which are latent

Testing whether the model (DAG) fits the observed data is then a way of validating or falsifying the causal hypothesis.

## As Scientific Infrastructure

Even outside Bayesian analysis, DAGs serve a function that [[Aneesh Sathe]] calls "laying out your thoughts." A DAG is a communicable representation of a scientific hypothesis — it can be checked, critiqued, and corrected by others.

This is the epistemic virtue Sathe contrasts with frequentist analysis: frequentist tests execute quickly, hiding their causal assumptions; DAGs make those assumptions legible.

## Connection to Judea Pearl

The modern theory of causal inference via DAGs is associated with [[Judea Pearl]] (*Causality*, 2000; *The Book of Why*, 2018), though Sathe does not cite Pearl explicitly. Pearl's do-calculus provides the formal machinery for inferring interventional effects from observational DAGs.

## Cross-References

- [[Bayesian Statistics]] — DAGs as the modeling scaffold
- [[Data Generating Process]] — what the DAG represents
- [[Causal Inference]] — the goal DAGs serve
- [[Transparency in Scientific Method]] — the meta-value DAGs embody
- [[Judea Pearl]] — the theoretical anchor for causal DAGs
- Source: [[My Road to Bayesian Stats]]
