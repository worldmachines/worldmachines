---
summary: "Across Bayesian statistics, explainable AI, and scientific method, Aneesh Sathe's essays converge on a single normative principle: making assumptions, causal models, and reasoning chains explicit is an epistemic virtue because it enables correction — and anything that hides assumptions is epistemically dangerous regardless of its output accuracy."
tags: [bayesian-statistics, explainable-ai, scientific-method, epistemology, transparency, synthesis]
last_updated: 2026-04-09
---

# Transparency as Epistemic Virtue

## The Convergence

Three separate essays by [[Aneesh Sathe]] arrive at the same normative principle from different domains:

1. **[[My Road to Bayesian Stats]]**: Bayesian inference is superior to frequentist statistics not primarily because it produces better results, but because it *forces explicit statement of causal assumptions* — making them open to inspection and correction. The t-test hides its assumptions; the Bayesian model exposes them.

2. **[[AI: Explainable Enough]]**: An AI system pitched at the right level of explanation creates an [[AI-Human Causal Prediction Machine]] where the AI exposes its causal reasoning (intermediate features) and the human can intercept and correct errors before they become decisions.

3. **[[My Grandfather Had Lore, My Father Had Google, I Have ChatGPT, My Son Will Have Lore]]**: LLMs are epistemically dangerous because they produce confident outputs with no verifiable provenance — the reasoning chain is hidden, so users cannot calibrate trust or detect errors.

## The Principle Stated

**Transparency of assumptions and causal reasoning is an epistemic virtue not because it makes outputs correct, but because it makes outputs correctable.**

The black box may be right — but the user has no way to know when it is wrong. The transparent model may be wrong — but the user can catch and fix the error.

## The Failure Modes of Opacity

| Domain | Opacity Failure |
|--------|----------------|
| Frequentist statistics | Hidden normality assumption produces false confidence with small samples |
| Black-box AI diagnosis | User cannot identify when feature extraction has failed |
| LLM outputs | Hallucination indistinguishable from accurate answer |
| Platform algorithms | Creator cannot understand why reward did or did not follow |

All four failures share a structure: the system produces an output without making its causal reasoning visible, so errors propagate undetected.

## The Structural Condition for Correction

[[Richard McElreath]]'s formulation: "There is no method for making causal models other than science. There is no method to science other than honest anarchy."

Honest anarchy means: the model is public, contestable, and revisable. This requires transparency. You cannot contest or revise what you cannot see.

## A Note on the Tension

Transparency has costs:
- Bayesian modeling is computationally and cognitively more expensive than running a t-test
- Calibrated explanation requires expensive human annotation at the intermediate feature level
- Full transparency can produce [[Unwarranted Faith in Numbers]] if users lack the statistical or domain literacy to evaluate what they see

The resolution: transparency must be *calibrated* to the audience's interpretive capacity — which is exactly the [[Calibrated Explanation]] principle. Transparency is not maximalism; it is relevance.

## Essay Seeds

- **"The Epistemic Compact"**: on the social contract of scientific communication — the obligation to expose assumptions so others can correct them, and why this compact is eroding (LLMs, vibes-based coding, significance-star culture)
- **"Honest Anarchy as Scientific Method"**: developing McElreath's phrase into a full account of how open, public, correctable theorizing constitutes science
- **"Black Boxes All the Way Down"**: a tour of hidden assumptions across domains — from NHST to neural networks to GDP accounting

## Cross-References

- [[Bayesian Statistics]] — the statistical instantiation
- [[Explainable AI]] — the AI instantiation
- [[DAG (Directed Acyclic Graph)]] — the formal tool for making DGPs transparent
- [[Data Generating Process]] — the concept that transparency is *about*
- [[Calibrated Explanation]] — the corrective to maximalist transparency
- [[AI-Human Causal Prediction Machine]] — the design target
- [[Unwarranted Faith in Numbers]] — the failure mode of miscalibrated transparency
- [[Richard McElreath]] — the intellectual anchor
- [[Hallucination]] — the failure mode opacity enables in LLMs
