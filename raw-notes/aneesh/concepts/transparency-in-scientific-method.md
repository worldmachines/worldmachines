---
summary: "The epistemic norm that scientific models, assumptions, and causal reasoning should be made explicit and public so that they can be inspected, challenged, and corrected — a norm that Bayesian statistics embodies and frequentist methods obscure."
tags: [scientific-method, bayesian-statistics, epistemology, transparency, causal-inference, reproducibility]
last_updated: 2026-04-09
---

# Transparency in Scientific Method

The epistemic norm that scientific models, assumptions, and causal reasoning must be made explicit and public — not because transparency guarantees correctness, but because it is the precondition for correction.

## The Norm

Science is self-correcting. But it can only correct what is visible. Transparency converts private assumptions into public objects that can be challenged. This is what distinguishes scientific claims from authoritative pronouncements.

## Bayesian Statistics as Embodiment

[[Bayesian Statistics]] makes this norm operational:
- The [[Data Generating Process]] must be stated as a [[DAG (Directed Acyclic Graph)]]
- The prior must be stated and defended
- The likelihood must be stated
- Model fit is checked against observed data — the model can fail and be revised

[[Frequentist Statistics]] obscures the norm:
- Normality and equal variance assumptions are hidden inside test procedures
- The "click t-test and see stars" workflow produces output with hidden assumptions that users cannot identify or contest

## Richard McElreath's Formulation

> "There is no method for making causal models other than science. There is no method to science other than honest anarchy."

"Honest anarchy" — not hierarchical authority, not established method followed without thought — the only scientific method is public, contestable, revisable theorizing. Honesty requires transparency of assumptions; anarchy means no assumption is above challenge.

## Reproducibility Crisis Connection

The reproducibility crisis in psychology, medicine, and social science is partly a transparency failure: p-hacking, hypothesizing after results are known (HARKing), and selective reporting are all enabled by hiding the process behind a reported output. Transparent pre-registration and open data are transparency interventions.

## Connection to Explainable AI

The same norm applies in AI: an AI system that produces confident outputs without exposing its causal reasoning fails the transparency norm. The [[AI-Human Causal Prediction Machine]] standard is a transparency norm applied to AI product design — expose the causal features so the expert can challenge and correct.

## Cross-References

- [[Bayesian Statistics]] — the statistical framework that embodies this norm
- [[Frequentist Statistics]] — the framework that obscures it
- [[DAG (Directed Acyclic Graph)]] — the formal tool for transparent causal modeling
- [[Data Generating Process]] — what transparency is about
- [[Richard McElreath]] — articulates the norm most sharply
- [[Explainable AI]] — the AI domain parallel
- [[Transparency as Epistemic Virtue]] — synthesis
- [[Scientific Reproducibility]] — related norm in the context of research replication
- Sources: [[My Road to Bayesian Stats]], [[AI: Explainable Enough]]
