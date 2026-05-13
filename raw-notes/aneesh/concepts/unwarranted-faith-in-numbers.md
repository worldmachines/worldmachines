---
summary: "An empirically documented cognitive failure in which people — including AI experts — perceive numerical outputs as signals of intelligence or reliability even when the numbers' meaning is opaque."
tags: [cognitive-bias, human-factors, explainable-ai, trust, decision-making, numeracy]
last_updated: 2026-04-09
---

# Unwarranted Faith in Numbers

An empirically documented failure mode in human-AI interaction: both AI experts and non-experts attribute intelligence or correctness to AI outputs *specifically because they are numerical*, even when the meaning of those numbers is not understood.

## The Study

Documented in research cited in [[Briefing: The State of Explainable AI (XAI)]]: participants shown numerical Q-values for robot actions perceived those values as signals of the robot's intelligence — even when the Q-values' interpretation was never explained. The more specific the number, the more credibility it appeared to convey.

This is a form of **pseudo-precision**: numbers convey apparent rigor even in the absence of actual comprehension.

## Why This Matters for XAI

The standard XAI instinct is: "explain by showing more." Unwarranted faith in numbers shows this backfires. If you add a confidence score (0.91), a SHAP attribution vector, or an IoU score to an AI output, users may:

1. Trust the output *more* than if no explanation were given
2. Suspend their own expert judgment in deference to the number
3. Fail to detect model errors that their domain expertise would have caught

This is the "explainability pitfall" (EP) that [[Seamful Design]] is designed to prevent.

## Connection to the Betty Crocker Principle

[[Aneesh Sathe]]'s formulation: adding an egg (meaningful user participation) is better than a fully automatic mix. Numerical outputs presented without user action opportunity produce passive acceptance — the AI equivalent of the fully automatic mix.

## Broader Pattern

Unwarranted faith in numbers is an instance of authority bias — numerical authority specifically. Related patterns:
- Automation bias: tendency to over-rely on automated systems
- Algorithmic aversion (the opposite): tendency to distrust algorithmic outputs entirely
- The numeracy gap: both effects are amplified when users lack statistical literacy

## Cross-References

- [[Seamful Design]] — the design remedy
- [[Calibrated Explanation]] — the alternative to numerical overload
- [[Explainable AI]] — the domain where this failure appears
- [[Human Factors Engineering (HFE)]] — the analytical framework that identifies EPs
- Source: [[Briefing: The State of Explainable AI (XAI)]]
