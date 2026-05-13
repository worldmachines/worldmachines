---
summary: "Karl Friston's framework in which organisms minimize variational free energy by updating internal models (perception) and acting on the world to make it conform to predictions (active inference)."
tags: [neuroscience, friston, free-energy, cognition, niche-construction]
last_updated: 2026-04-10
---

# Active Inference

**Active inference** is Karl Friston's extension of the free energy principle to action. Organisms minimize variational free energy — a bound on surprise or prediction error — through two complementary channels: **updating internal models** to better predict sensory input (perception), and **acting on the world** to make it conform to existing predictions (active inference proper). The framework unifies perception, action, learning, and attention under a single variational objective.

## The Formal Version of "Ideas Upstream of Atoms"

Active inference provides the formal apparatus for a claim that recurs across this wiki: that internal models are causally upstream of material rearrangement. An organism does not merely passively model the world and then act on separate motivational grounds. Instead, the generative model *is* the source of action — the organism acts to minimize the divergence between predicted and observed states. Ideas (encoded as prior beliefs in the generative model) literally cause the physical world to be rearranged.

This is not metaphor. In the free energy formalism, action and perception are mathematically symmetric operations on the same objective function. The asymmetry is only in direction: perception adjusts the model to match the world; action adjusts the world to match the model.

## Niche Construction

Active inference extends naturally to **niche construction**: organisms do not merely adapt to environments but reshape environments to mirror their internal causal models. A beaver builds a dam not because it has a "dam-building module" but because its generative model predicts a world with a dam, and the discrepancy between prediction and reality drives dam-building behavior. The environment becomes an extension of the organism's model — a physical instantiation of its expectations.

This dissolves the organism-environment boundary in a way that parallels [[extended-mind]] from the philosophical side: if the organism's model extends into the environment through niche construction, then the environment is part of the cognitive system.

## Key Technical Details

- **Variational free energy** is an upper bound on surprisal (negative log evidence). Minimizing it amounts to maximizing model evidence — making the organism's model an increasingly accurate account of its sensory world.
- **Expected free energy** extends this to the future: organisms select actions that minimize *expected* surprise, which decomposes into an epistemic (information-seeking) and pragmatic (goal-seeking) component.
- The framework subsumes reinforcement learning, optimal control, and Bayesian inference as special cases.

## Connections

- [[extended-mind]]: Clark and Chalmers dissolve the skull boundary philosophically; active inference dissolves it formally — the generative model recruits environmental states as part of its inference.
- [[capture-resistance]]: If organisms act to maintain their generative models, then capture resistance is the refusal to let external agents overwrite the organism's priors — the formal version of liveness.
- [[energy-rate-density]]: More complex generative models require more energy throughput to maintain, linking active inference to Chaisson's thermodynamic complexity metric.
