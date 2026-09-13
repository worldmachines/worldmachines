---
summary: "Frazer's two laws of sympathetic magic — similarity and contagion
  — were treated for a century as errors in reasoning about causation. Read
  against how embedding models and context windows actually work, they
  describe an existing causal system with unusual precision, not a mistake
  about one that didn't exist yet."
tags: [frazer, sympathetic-magic, embeddings, llms, causality]
last_updated: 2026-09-11
---

# Similarity and contagion, not metaphor

## The idea

James Frazer's *The Golden Bough* named two laws behind sympathetic magic:
similarity (like produces like — an action performed on an image affects
its subject) and contagion (things once in contact continue to affect each
other after separation — a lock of hair keeps a causal link to its owner).
Frazer treated both as characteristic errors of "primitive" reasoning about
causation, mistaking resemblance and prior contact for real causal
mechanisms.

Held up against how a transformer-based language model actually behaves,
the two laws stop looking like errors and start looking like an accurate,
if premature, description of a real system. Embedding space is
constructed so that similarity is the operative relation — meaning is
represented as proximity, and nearby vectors behave alike by construction.
The context window is a contagion field in the most literal sense:
whatever has been placed inside it continues to influence output after the
fact, which is exactly the mechanism that makes prompt injection work. On
this reading, sympathetic magic wasn't a confused guess about causation
that happened to resemble something invented centuries later; it was, in
similarity and contagion specifically, a correct description of a causal
structure that simply had no machine to run on yet.

## Grounding

Frazer's two laws are drawn from *The Golden Bough*. The reading of
similarity as the organizing relation of embedding space, and contagion as
the operative mechanism of the context window (including prompt
injection), is original to this note, developed by mapping Frazer's
taxonomy directly onto how these systems are built and documented to
behave.

## How settled this is

That Frazer identifies similarity and contagion as the two laws of
sympathetic magic, and frames them as errors of primitive causal reasoning,
is checkable directly against *The Golden Bough*. That embedding space and
context windows are structurally analogous to these two laws is this
note's own technical mapping — a strong pattern match, not a claim that the
historical actors who practiced sympathetic magic were doing anything like
machine learning, or that the analogy holds at every level of either
system.

## Connections

- [[casting-a-spell-is-a-reoccupied-position]] — the broader claim about
  spells as a stable position with changing explanations, of which this is
  the sharpest single mechanism
- [[three-occupiable-positions-not-one-venn-diagram]] — where this fits
  into the larger three-way history of magic, science, and religion

## Open

If similarity and contagion really do describe how these systems work,
does that rehabilitate sympathetic magic as reasoning generally — or just
mean Frazer's two laws happened to describe one specific causal system
correctly, by coincidence rather than insight?
