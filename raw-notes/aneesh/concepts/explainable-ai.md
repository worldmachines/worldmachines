---
summary: "The principle that AI systems must expose their reasoning chain so users can audit, override, or calibrate trust — treated by Sathe as the minimum standard for AI in critical applications; expanded by XAI research into methods, design standards, and responsible AI frameworks."
tags: [ai-safety, epistemics, transparency, healthcare-ai, trust, XAI, responsible-ai, human-factors]
last_updated: 2026-04-09
---

# Explainable AI (XAI)

## Definition

Explainable AI (XAI) refers to AI systems whose outputs are accompanied by accessible reasoning chains, citations, or structured evidence that allow users to evaluate the basis for a conclusion. The standard is epistemic: a user should be able to apply their own judgment to the AI's answer and know when to override it.

## Historical Roots

The XAI problem is old: **MYCIN** (1970s) was among the first medical expert systems and famously couldn't explain its numerical reasoning to physicians. Despite decades of accumulated knowledge in philosophy, psychology, and cognitive science about how people form understanding, the XAI field as named emerged around 2016 and has been slow to incorporate that inheritance.

## Why It Matters

In Sathe's framing (see [[My Grandfather Had Lore]]), explainability is not a nice-to-have but the precondition for AI being usable in any domain where errors have consequences. The specific failure of LLMs is that they produce answers with high surface confidence but no verifiable provenance. Users "instinctively accept" confident outputs as truth — which is dangerous when the underlying source could be hallucinated.

In [[Dancing on the Shoulders of Giants]], [[Knowledge Graphs]] are positioned as the primary mechanism delivering explainability: KGs store not just data but typed relationships and metadata, making reasoning paths auditable.

## The XAI Credibility Gap

Most XAI research optimizes for **technical faithfulness** — does the explanation accurately represent the model's internal mechanics? — rather than **human usefulness** — does the explanation improve decision quality? This is a field-level miscalibration documented in [[Briefing: The State of Explainable AI (XAI)]].

## The "Explainable Enough" Standard

[[Aneesh Sathe]] in [[AI: Explainable Enough]] offers a product-design corrective: pitch explanation at the *lowest level of detail the domain expert actually cares about* — neither full architecture nor bare verdict. The goal is an [[AI-Human Causal Prediction Machine]] that surfaces intermediate features (causes) so the expert can confirm, catching AI errors before they become decisions.

- Too much: IoU scores and architecture details glaze over expert users
- Too little: verdict-only excludes the user from causal reasoning and raises regulatory risk
- Sweet spot: "it's likely disease X because features A, B, C" — the expert's vocabulary level

## Key XAI Methods and Their Problems

- **[[SHAP]]** (SHapley Additive exPlanations): game-theoretic feature attribution — widely used, but lacks a "utility" concept and produces misleading scores in non-linear models
- **[[LIME]]** (Local Interpretable Model-agnostic Explanations): local surrogate approximation — same limitations
- **[[Contextual Importance and Utility (CIU)]]**: addresses both weaknesses by quantifying how feature importance *and* value favorability shift with context
- **[[Counterfactual Explanations]]**: "what would need to change?" — useful for deliberative human decision-making
- **[[GradCAM]]**: gradient-based visual explanations for CNNs

## The Disagreement Problem

A critical operational failure: different XAI methods routinely produce **conflicting feature attributions** for the same model. Practitioners rank this the most trust-eroding failure (36.5% rate it most severe) even though it appears in only ~2% of reported issues by volume — because it strikes after adoption. See [[Briefing: The State of Explainable AI (XAI)]].

## Human Factors Pitfalls

[[Human Factors Engineering (HFE)]] documents "explainability pitfalls" (EPs): unintended negative effects of adding explanation. Key finding: both experts and non-experts show **[[Unwarranted Faith in Numbers]]** — numerical outputs are perceived as intelligence signals even when their meaning is opaque. Remedy: [[Seamful Design]] — strategic information disclosure that aids understanding and conceals distraction.

## Responsible AI Frame

XAI sits within a broader **[[Responsible AI (RAI)]]** framework with four pillars: ethics, explainability, privacy/security, and trustworthiness as emergent property. Key distinction for human decision-makers: **explanation** (understanding AI internals) vs. **justification** (external evidence supporting output) — both required when a human must defend a choice.

## Mechanisms

- **Citation-backed generation**: [[Perplexity AI]] attempts to retrofit citations onto LLM outputs; Sathe is cautiously skeptical.
- **KG-grounded retrieval**: When the answer is retrieved from a knowledge graph rather than generated from latent weights, the path is traceable.
- **RAG pipelines**: [[Retrieval-Augmented Generation]] can improve explainability by grounding generation in retrieved passages, but basic RAG over flat text still obscures relational reasoning.

## Tensions

- Explainability and capability trade off: the most powerful models tend to be the least interpretable.
- "Citation" does not equal "correctness" — a model can cite a source it has misrepresented.
- [[Mission-Critical AI]] contexts (healthcare, defense) demand explainability most, but also attract investment in the most powerful opaque models.
- The field's organizational/methodological problems (documentation, best-practice guidance, method disagreement) are not solvable through purely technical XAI advances.

## Related Concepts

- [[Hallucination]] — the failure mode explainability is meant to mitigate
- [[Citation Problem in LLMs]] — the specific absence that Perplexity and RAG try to address
- [[Knowledge Graphs]] — structural approach to grounded, auditable AI
- [[Composite AI Architecture (Experts + LLM + KG)]] — explainability through KG integration
- [[Calibrated Explanation]] — the design standard for domain-appropriate depth
- [[AI-Human Causal Prediction Machine]] — the positive design target
- [[Seamful Design]] — strategic information design philosophy
- [[Responsible AI (RAI)]] — broader governance frame
- [[Transparency in Scientific Method]] — the parallel principle in statistical inference
- Sources: [[My Grandfather Had Lore]], [[AI: Explainable Enough]], [[Briefing: The State of Explainable AI (XAI)]]
