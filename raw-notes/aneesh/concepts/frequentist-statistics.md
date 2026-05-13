---
summary: "The dominant statistical paradigm in which probability is defined as the long-run frequency of events; associated with p-values, null hypothesis significance testing, and assumptions of normality — a paradigm critiqued for hiding assumptions and being logically incapable of affirming the null hypothesis."
tags: [statistics, frequentist, p-values, null-hypothesis, scientific-method, epistemology]
last_updated: 2026-04-09
---

# Frequentist Statistics

The dominant statistical paradigm in 20th-century science, in which probability is defined as the *long-run relative frequency* of events in repeated experiments. Does not assign probabilities to hypotheses — only to data given a null hypothesis (P(data | H₀)).

## Core Mechanisms

- **Null hypothesis significance testing (NHST)**: test whether the data would be unlikely if a null hypothesis were true
- **p-value**: P(data as extreme as observed | null is true). A low p-value rejects the null; it does not confirm the alternative
- **Significance threshold**: conventionally p < 0.05, but threshold choice is arbitrary
- **Assumptions**: most tests assume normality and equal variance in the underlying population

## Key Logical Limitations (from [[Aneesh Sathe]]'s critique)

1. **Cannot accept the null hypothesis**: can only fail to reject it — you can never conclude "there is no difference"
2. **Cannot confirm the alternative**: low p-value shows evidence against the null, not evidence for an alternative model
3. **Cannot communicate uncertainty quantitatively**: p-values do not indicate the probability the hypothesis is true
4. **Minimum sample size requirements**: t-tests perform poorly with small samples; biological experiments often cannot meet this threshold
5. **Hidden assumptions**: normality and equal variance assumptions are enforced by the test selection, without explicit statement — a kind of epistemic smuggling

## The Significance Stars Problem

The proliferation of "***" notation has created a cultural shortcut that Sathe describes as "you put in your data, click t-test, and woosh, you see stars." This shortcuts genuine causal reasoning, creating the appearance of scientific rigor without the substance.

## Why It Remains Dominant

- Computational simplicity (pre-computer era statistics)
- Institutional inertia (journals, training, peer review conventions)
- Faster communication: results can be stated as a single threshold pass/fail

## Cross-References

- [[Bayesian Statistics]] — the proposed alternative
- [[P-Value Problem]] — the specific failure of significance testing
- [[Transparency in Scientific Method]] — the meta-value frequentism fails
- [[Data Generating Process]] — the concept frequentism ignores
- [[Causal Inference]] — the goal frequentism cannot reach
- Source: [[My Road to Bayesian Stats]]
