---
summary: "A design philosophy from Human Factors Engineering that strategically reveals information that aids understanding and conceals information that distracts, to produce deliberate rather than automatic decision-making."
tags: [explainable-ai, human-factors, UX, design, cognitive-science, decision-making]
last_updated: 2026-04-09
---

# Seamful Design

A design philosophy developed in Human Factors Engineering (HFE) as a response to the failure of AI transparency. Seamful design *strategically reveals* information that aids user understanding and *strategically conceals* information that distracts or induces over-trust — rather than maximizing transparency (revealing everything) or minimizing it (black box).

## Origin in HFE

The term "seamful" contrasts with "seamless" — the conventional UX aspiration of removing friction. Seamful design argues that well-placed cognitive friction, or "seams," serves a function: it forces the user into deliberate, System 2 reasoning rather than automatic System 1 acceptance.

Applied to XAI: not all information about an AI's output is useful. Some information (intermediate features in the user's vocabulary) builds confidence. Other information (raw confidence scores, architecture details) induces **[[Unwarranted Faith in Numbers]]** — a documented failure mode where numerical outputs are perceived as intelligence signals even when their meaning is opaque.

## Practical Tools

- **Counterfactual ("what-if") explanations**: "if feature X were different, the output would change to Y" — introduces productive uncertainty and invites deliberate judgment
- **Selective feature display**: show the 3–5 features most relevant to the user's decision, not a full attribution vector
- **Confidence communication**: frame uncertainty in ways the domain expert can evaluate, not as raw probability scores

## Connection to Calibrated Explanation

Seamful design is the broader design philosophy of which [[Calibrated Explanation]] is an instance. The Betty Crocker egg principle is a seamful design move: leaving the user one cognitive action to perform.

## Cross-References

- [[Explainable AI]] — the domain where seamful design is applied
- [[Calibrated Explanation]] — the XAI-specific application
- [[Unwarranted Faith in Numbers]] — the failure mode seamful design prevents
- [[Counterfactual Explanations]] — a concrete seamful design tool
- [[Human Factors Engineering (HFE)]] — the originating discipline
- Source: [[Briefing: The State of Explainable AI (XAI)]]
