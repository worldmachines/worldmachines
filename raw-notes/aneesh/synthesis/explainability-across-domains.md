---
summary: "The same design problem — how much to explain, to whom, and at what level of abstraction — appears in statistical modeling, AI product design, and scientific communication; the shared solution is calibration to the audience's interpretive level, not maximum or minimum transparency."
tags: [explainable-ai, bayesian-statistics, scientific-method, design, synthesis, calibration]
last_updated: 2026-04-09
---

# Explainability Across Domains

## The Parallel Problems

The same structural problem appears independently across three domains in Sathe's essays:

### 1. Statistical Analysis
A biologist running a t-test gets "***" with no visibility into assumptions about normality, sample size adequacy, or the shape of the underlying distribution. [[Bayesian Statistics]] forces explicit statement of the [[Data Generating Process]] — but at the cost of more modeling work and a more complex output (a posterior distribution rather than a p-value).

### 2. AI Product Design
A deep learning model classifies a pathological image as "malignant." The biologist or clinician gets a verdict with no intermediate features. [[Calibrated Explanation]] requires pitching the output at the expert's vocabulary level — "features A, B, C are present" — not the model's vocabulary (confidence scores, IoU).

### 3. XAI Research
The field optimizes for *technical faithfulness* (does the explanation match model internals?) rather than *human usefulness* (does it improve decision quality?). Conflicting SHAP and LIME attributions for the same model erode trust after adoption.

## The Shared Structure

In each case:
- **The black box failure**: output without reasoning chain → user cannot catch errors
- **The over-explanation failure**: maximum transparency → user overwhelmed, or [[Unwarranted Faith in Numbers]] triggered
- **The calibration solution**: explanation pitched at the audience's interpretive level and decision need

## The Audience Determines the Level

| Domain | Audience | Right Level |
|--------|----------|-------------|
| Bayesian stats | Domain scientist | DAG and key assumptions — not full posterior math |
| Medical AI | Clinician | Intermediate features in clinical vocabulary — not IoU or model architecture |
| XAI for practitioners | ML engineer | Guidance on method disagreement — not full faithfulness proofs |
| LLM outputs | General user | Source citations and confidence — not attention weights |

The correct level of explanation is not a property of the explanation method; it is a property of the audience-task pair.

## The Betty Crocker Principle Generalized

[[Aneesh Sathe]]'s Betty Crocker metaphor (add the egg) generalizes: in every domain, leave the user one meaningful cognitive action that:
1. Builds ownership and engagement
2. Creates an error-interception opportunity
3. Preserves the human's sense of judgment and accountability

In Bayesian stats: the scientist chooses the prior and checks model fit. In medical AI: the clinician confirms the intermediate features. In LLM use: the expert verifies citations and challenges reasoning chains.

## The Deeper Connection

Both the Bayesian and AI explainability arguments are ultimately about **causal reasoning**. The Bayesian DAG is a causal model. The AI-Human Causal Prediction Machine surfaces the causes behind predictions. The XAI credibility gap is largely a failure to expose causal reasoning.

See [[Transparency as Epistemic Virtue]] for the normative synthesis.

## Essay Seeds

- **"The Right Level of Detail"**: a unified treatment of calibrated explanation across scientific communication, AI design, and statistical modeling
- **"Causes All the Way Down"**: why causal transparency — not just any transparency — is the standard that matters
- **"The Expert's Eye"**: on the domain expert as the essential calibration point for AI systems

## Cross-References

- [[Calibrated Explanation]] — the design principle
- [[Bayesian Statistics]] — statistical instantiation
- [[Explainable AI]] — AI instantiation
- [[AI-Human Causal Prediction Machine]] — design target
- [[Seamful Design]] — related design philosophy
- [[Unwarranted Faith in Numbers]] — the failure mode of miscalibrated transparency
- [[Transparency as Epistemic Virtue]] — normative synthesis
- [[Data Generating Process]] — the shared underlying concept
- Sources: [[My Road to Bayesian Stats]], [[AI: Explainable Enough]], [[Briefing: The State of Explainable AI (XAI)]]
