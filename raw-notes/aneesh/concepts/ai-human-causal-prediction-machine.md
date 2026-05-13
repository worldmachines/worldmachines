---
summary: "Aneesh Sathe's term for the ideal human-AI system: AI surfaces intermediate causal features, the human expert confirms and applies judgment, and the final decision remains with the human — a collaborative causal reasoning loop."
tags: [explainable-ai, AI-design, human-computer-interaction, causality, medical-ai]
last_updated: 2026-04-09
---

# AI-Human Causal Prediction Machine

[[Aneesh Sathe]]'s term for the ideal architecture of human-AI collaborative decision-making, developed in [[AI: Explainable Enough]].

## The Design

1. **AI identifies intermediate features** — the causes, not just the conclusion. ("Features A, B, C are present" rather than "diagnosis: malignant")
2. **Human expert evaluates the features** — using their domain knowledge, they confirm or challenge whether A, B, C are present and whether they support the conclusion
3. **Human makes the final prediction/decision** — the causal chain is completed by a human judgment, not auto-executed
4. **If AI is wrong, the error is catchable** — because the causal reasoning is exposed, the expert can intercept before the error becomes a decision

## Why "Causal"

The word is deliberate: the features are the *causes* of the predicted outcome. This is distinct from:
- Correlation-based highlighting (which features were associated with this output?)
- Post-hoc attribution (which features *would have* changed the output?)

Exposing causal features gives the human expert the ability to reason from first principles, not just ratify a statistical pattern.

## Connection to Bayesian Thinking

The AI-Human Causal Prediction Machine is structurally parallel to Bayesian statistical reasoning: the AI provides a model of causality (posterior over features given data), the human provides domain knowledge (the prior), and the final conclusion is a human-AI synthesis. See [[Transparency as Epistemic Virtue]] for the synthesis.

## Contrast With

- **Black box verdict-only AI**: excludes human from causal reasoning; increases regulatory risk
- **Full architecture transparency**: overwhelms human with technically accurate but cognitively unusable information
- **Vibe coding analogy**: code generation as opposed to direct execution — the programmer must verify the code, preserving human causal agency

## Real-World Case

Sathe's own microscopy work: biologists in 2015 would not accept deep learning outputs that couldn't be explained. The solution was not to explain the deep learning model — it was to identify the intermediate features the biologist already reasoned in terms of, and surface those.

## Cross-References

- [[Calibrated Explanation]] — the design standard that produces this architecture
- [[Explainable AI]] — the broader domain
- [[Causal Inference]] — the epistemic goal
- [[Transparency as Epistemic Virtue]] — synthesis connecting to Bayesian statistics
- [[Seamful Design]] — the design philosophy that enables it
- Source: [[AI: Explainable Enough]]
