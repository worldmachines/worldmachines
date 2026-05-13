---
summary: "The design principle that AI explanations should be pitched at the lowest level of detail a domain expert actually cares about — neither architecture-level nor verdict-only — producing an AI-human causal prediction machine."
tags: [explainable-ai, UX, product-design, human-computer-interaction, AI-design]
last_updated: 2026-04-09
---

# Calibrated Explanation

The design principle articulated by [[Aneesh Sathe]] in [[AI: Explainable Enough]]: AI explanations should be calibrated to the *domain expert's vocabulary and cognitive level* — specifically, the lowest level of detail they actually care about.

## The Three-Level Problem

| Level | Example | Problem |
|-------|---------|---------|
| Too deep | "IoU score: 0.82, detected by YOLOv7 at confidence 0.91" | Expert's eyes glaze; meaningless to a biologist or clinician |
| Just right | "Features A, B, C detected → likely disease X" | Expert can verify, override, build confidence |
| Too shallow | "Diagnosis: malignant" | Expert excluded from causal chain; regulatory risk; no learning |

The "just right" level is what Sathe calls the **intermediate feature level** — the causes that lead to the conclusion, expressed in the expert's own vocabulary.

## The Betty Crocker Principle

Like the cake mix that requires the customer to add one egg (participation that builds ownership and catches errors), AI should leave a meaningful cognitive action for the user. Full automation — like a cake mix that requires no input — produces passive acceptance rather than expert judgment.

## Why This Is Hard to Build

Generating ground-truth labels at the intermediate feature level is expensive and domain-specific. It requires:
- Domain experts to annotate not just outcomes but intermediate features
- Human-in-the-loop labeling at the right level of abstraction
- Resisting the easier paths: predicting the whole image (cheaper) or outputting raw model internals (default)

## Design Implications

- The intermediate feature level is discovered through customer research, not assumed
- Different user populations have different calibration points (clinician vs. patient vs. regulator)
- As AI performance improves and users become more sophisticated, the calibration point may shift

## Cross-References

- [[Explainable AI]] — the broader domain
- [[AI-Human Causal Prediction Machine]] — the target system this creates
- [[Domain Expert User]] — the calibration audience
- [[Seamful Design]] — adjacent design philosophy (strategic information disclosure)
- [[Unwarranted Faith in Numbers]] — the failure mode to avoid
- Source: [[AI: Explainable Enough]]
