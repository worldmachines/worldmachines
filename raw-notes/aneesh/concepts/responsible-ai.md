---
summary: "A governance framework for AI systems built on four pillars — ethics, explainability, privacy/security, and trustworthiness — where trustworthiness is an emergent property of the other three, not a separate technical property."
tags: [responsible-ai, AI-governance, ethics, explainability, trustworthiness, regulation]
last_updated: 2026-04-09
---

# Responsible AI (RAI)

A governance and design framework for AI systems that treats trustworthiness not as a single technical property but as an emergent outcome of four jointly-satisfied pillars.

## The Four Pillars

1. **Ethics**: fairness, accountability, compliance with applicable norms and laws
2. **Explainability**: users can understand why a system made a decision (see [[Explainable AI]])
3. **Privacy-preserving and secure AI**: data minimization, adversarial robustness, confidentiality
4. **Trustworthiness**: emerges from the other three — not achievable by optimizing for trust directly

## Key Distinction: Explanation vs. Justification

For a human decision-maker who must defend a choice to others:
- **Explanation**: understanding the AI's internal process — how it arrived at its output
- **Justification**: external evidence supporting the AI's output — why the output is correct

Both are required. A user who understands the model but has no external validation is underequipped. A user with external evidence but no process understanding cannot catch model errors.

## AI as Empowerment Tool

RAI frames AI in high-stakes decision-making as an **empowerment tool** — the human retains accountability and must be able to justify decisions. This is opposed to AI-as-authority, where the human defers to the AI's judgment.

This framing has direct implications for [[Calibrated Explanation]]: the explanation must enable the human to exercise and justify judgment, not merely accept or reject a verdict.

## Open Problems

- Longitudinal studies: most XAI evaluations are point-in-time; long-term effects on trust and decision quality are understudied
- Interdisciplinary collaboration: RAI requires philosophy, psychology, law, and computer science — rarely integrated
- Standardized benchmarks: RAI requirements differ across domains; common evaluation frameworks don't yet exist

## Cross-References

- [[Explainable AI]] — the second pillar
- [[Calibrated Explanation]] — how explainability is operationalized at the product level
- [[Seamful Design]] — a design approach aligned with RAI principles
- [[Unwarranted Faith in Numbers]] — a failure case RAI must anticipate
- [[Transparency in Scientific Method]] — parallel principle in research methodology
- Source: [[Briefing: The State of Explainable AI (XAI)]]
