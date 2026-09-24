---
summary: "A research briefing on the state of Explainable AI (XAI), identifying a credibility gap between technical faithfulness and human usefulness, the disagreement problem between XAI methods, and the framing of XAI within Responsible AI."
tags: [explainable-ai, responsible-ai, human-factors, decision-making, SHAP, LIME, CIU, XAI]
last_updated: 2026-04-09
---

# Briefing: The State of Explainable AI (XAI) and Its Impact on Human-AI Decision-Making

**Source**: [aneeshsathe.com, 2025-07-24](https://aneeshsathe.com/briefing-the-state-of-explainable-ai-xai-and-its-impact-on-human-ai-decision-making/)
**Author**: [[Aneesh Sathe]]

## Central Argument

The XAI field has a structural credibility gap: it optimizes for technical faithfulness to model internals rather than measurable usefulness to human decision-makers. Despite roots in the 1970s (MYCIN), XAI largely ignores decades of philosophy, psychology, and cognitive science. The field also has an underacknowledged **disagreement problem** — different XAI methods produce conflicting feature attributions for the same model, which practitioners identify as the most trust-eroding failure mode even though it's statistically rare. The solution space is more organizational and methodological than technical.

## Key Sections

### The XAI Credibility Gap
- Field emerged ~2016 as a major research focus; roots in MYCIN (1970s)
- Most research optimizes "faithfulness" (does the explanation match model internals?) rather than usefulness
- Ignores accumulated knowledge from philosophy, psychology, cognitive science about how people actually form understanding

### Explanations as Means, Not Ends
- Grounded in **statistical decision theory**: an explanation has value only if it measurably improves performance on a concrete task
- Three metrics proposed:
  1. Theoretical ceiling: what a perfectly rational agent could gain
  2. Potential gain: information the human doesn't already have
  3. Actual behavioral improvement: observed in controlled experiments
- **[[Contextual Importance and Utility (CIU)]]**: a framework that quantifies how feature importance *and* favorability of its value shift with context — addresses a core weakness of [[SHAP]] and [[LIME]], which lack a "utility" concept and produce misleading scores in non-linear models

### The Disagreement Problem
- Stack Overflow dataset analysis of practitioner challenges
- Different XAI methods routinely produce conflicting feature attributions for the same model
- Model integration issues: most common technical barrier (31% prevalence)
- Visualization problems: 30% prevalence
- Compatibility failures: 20% prevalence
- **Disagreement between methods**: only ~2% of reported issues by volume, but ranked most severe by 36.5% of practitioners — because it strikes after adoption and directly erodes trust

### Human Factors and Unintentional Harm
- **[[Human Factors Engineering (HFE)]]** as a framework for "explainability pitfalls" (EPs): unintended negative consequences of adding explanations
- Study finding: both AI experts and non-experts displayed **"unwarranted faith in numbers"** — Q-values for robot actions perceived as intelligence signals even when opaque
- Remedy: **[[Seamful Design]]** — strategically revealing information that aids and concealing information that distracts
- **Counterfactual ("what-if") explanations** as tools for introducing productive cognitive friction and deliberate rather than automatic thinking
- Shift: from acceptance-driven AI adoption toward critical reflection

### What Practitioners Actually Want
- Better documentation and tutorials (55.8% strongly agree)
- Clearer best-practice guidance (48.1%)
- Simplified configuration and setup (40.4%)
- Explicit guidance on how to handle disagreements between XAI methods
- These are organizational/methodological problems, not purely technical

### Responsible AI as the Frame
- XAI inside a **[[Responsible AI (RAI)]]** framework with four pillars:
  1. Ethics (fairness, accountability, compliance)
  2. Explainability
  3. Privacy-preserving and secure AI
  4. Trustworthiness as emergent property of the first three
- Key distinction: **explanation** (understanding AI's internal process) vs. **justification** (external evidence supporting AI's output) — both required for human decision-makers who may need to defend choices
- Open problems: longitudinal studies, interdisciplinary collaboration, standardized benchmarks for RAI requirements

## What's Missing

- Doesn't engage with the political economy of who funds and controls XAI research (predominantly industry labs with product incentives)
- No discussion of cases where explanation actively *misleads* rather than merely failing to help
- Limited engagement with non-Western regulatory contexts (EU AI Act gets no mention)

## Cross-References

- [[Explainable AI]] — central domain
- [[SHAP]] — widely used attribution method, critiqued here
- [[LIME]] — widely used attribution method, critiqued here
- [[Contextual Importance and Utility (CIU)]] — proposed alternative
- [[Seamful Design]] — design philosophy from HFE
- [[Responsible AI (RAI)]] — broader framing
- [[Human Factors Engineering (HFE)]] — analytical framework for explainability pitfalls
- [[MYCIN]] — historical precedent (1970s medical AI)
- [[Counterfactual Explanations]] — practical tool for productive friction
- [[Unwarranted Faith in Numbers]] — empirical finding on over-trust
- Related summary: [[AI: Explainable Enough]] — Sathe's product-practice companion piece
- Synthesis: [[Explainability Across Domains]] — the shared design challenge
- Synthesis: [[Transparency as Epistemic Virtue]] — the normative throughline
