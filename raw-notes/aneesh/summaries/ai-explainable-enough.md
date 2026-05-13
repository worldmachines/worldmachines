---
summary: "Aneesh Sathe argues from product experience that AI must be 'explainable enough' — calibrated to the cognitive level of the domain expert user — rather than fully transparent or fully opaque, yielding an AI-human causal prediction machine."
tags: [explainable-ai, human-computer-interaction, deep-learning, product-design, medical-ai, user-experience]
last_updated: 2026-04-09
---

# AI: Explainable Enough

**Source**: [aneeshsathe.com, 2025-07-23](https://aneeshsathe.com/ai-explainable-enough/)
**Author**: [[Aneesh Sathe]]

## Central Argument

The right level of AI explainability is neither full technical transparency nor a black-box verdict. It is the *lowest level of detail the domain expert actually cares about*. The essay coins an implicit standard — "explainable enough" — anchored in customer interviews from biomedical AI product development: expose the intermediate features (e.g., "juicy" fruit), not the architecture (IoU scores, YOLO vs. R-CNN), not just the final answer. The goal is an **AI-Human causal prediction machine** where the AI surfaces causes, the human confirms, and the decision remains with the human.

## Key Claims

1. **The sweet spot problem**: both too much and too little explanation fail. Too much (architecture details) glazes over expert users; too little (verdict-only) excludes the user from causal reasoning and raises regulatory risk.
2. **Domain expertise is the calibration standard**: biologists don't want confidence scores — they want to see the features (A, B, C) that lead to a diagnosis. The explanation should be pitched at the expert's vocabulary.
3. **The "add the egg" principle**: like the Betty Crocker cake mix that requires the customer to add one egg, AI should leave a meaningful action for the user — participation builds confidence and catches errors.
4. **LLMs and code generation as a case**: LLMs generate code rather than directly executing it because the programmer needs to verify it. The programmers' ability to spot AI errors is the explainability mechanism.
5. **[[REX]]** — mentioned as a promising development that "retro-fits causality onto usual deep learning models": a path toward natively causal explanations without bespoke feature engineering.
6. **Explainability-enough is hard and expensive**: generating ground-truth labels at the correct intermediate level of abstraction — not full diagnosis, not raw pixel scores — requires intensive human annotation effort. This is a product engineering challenge, not merely a research one.

## Origin Story

The insight emerged from:
- Microscopy and bio background → image analysis → deep learning (2015)
- Biologists refusing to accept deep learning results they couldn't understand
- Customer interview where a user's natural language ("They look really juicy") revealed the correct intermediate abstraction level

## What's Missing

- No treatment of *who decides* what the right level of detail is — especially in multi-stakeholder settings (clinician, patient, regulator all differ)
- Doesn't engage with formal XAI methods (SHAP, LIME, GradCAM) — the companion briefing [[Briefing: The State of Explainable AI (XAI)]] covers this
- No discussion of how "explainable enough" changes over time as user mental models mature
- Vibe coding mentioned in passing but not developed as a case study of explainability tradeoffs

## Cross-References

- [[Explainable AI]] — the research domain this essay rethinks
- [[AI-Human Causal Prediction Machine]] — the positive design target
- [[Calibrated Explanation]] — the core design principle
- [[Domain Expert User]] — the design-audience concept
- [[REX (Retroactive Explanation)]] — cited technical development
- [[Black Box AI]] — the failure mode being avoided
- [[Regulatory Risk in Medical AI]] — implicit constraint on explanation depth
- Synthesis: [[Transparency as Epistemic Virtue]] — connects to Bayesian transparency argument
- Synthesis: [[Explainability Across Domains]] — shared principles between medical AI and statistical modeling
