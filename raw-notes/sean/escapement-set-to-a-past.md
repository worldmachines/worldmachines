---
summary: "AI is kept reliable by clamping its wide range to the band where
  it behaves well, but that band is the training distribution - an archived
  past - while the world it operates in keeps moving, so the difficulty
  migrates from raw model capability to permanent freshness maintenance:
  retrieval, continual learning, and evaluations that themselves rot."
tags: [ai, training-distribution, drift, evals, bet-table, circular-error]
last_updated: 2026-09-05
---

# The escapement set to a past

## The idea

The same move that makes an AI model useful - restricting it to the region
of behavior it was trained on, the way an anchor escapement restricts a
pendulum's swing to the arc where circular error is negligible - has a cost
that does not show up immediately: the restricted band is the archived
past, and the world the model operates in is not stationary. The practical
acceptance this requires is that the model is always somewhat stale, that
shipping on an imperfect archive is unavoidable, and that keeping the model
current is a permanent maintenance cost rather than a problem that gets
solved once. The failure mode is quiet rather than dramatic: the reliable
band drifts off the world it was fitted to, and the model becomes
confidently right about a world that no longer exists, with no built-in
signal that this has happened.

## Where it comes from

One row ("The escapement set to a past") of the same Divergence Machine
bet-table.

## How settled this is

A working hypothesis; the associated bets (that "context rot" and "eval
rot" become standard terms, that data recency becomes a premium good, that
continual learning becomes the frontier spend) are stated as testable
near-term predictions.

## Connections

- [[circular-error]] - this row is a direct, named application of that
  essay's own AI-scaffolding argument: this is exactly what an anchor
  escapement around a raw model looks like, restated as a specific
  structural error
- [[escapement-as-transducer]] - the mechanical image both notes borrow,
  applied here to a training distribution rather than to a pendulum's swing
- [[near-term-bets-of-the-divergence-machine]] - several of the grouped
  near-term bets (context rot, eval rot) are direct downstream consequences
  of this error

## Open

Whether "currency as a permanent maintenance cost" is something
institutions will actually budget for consistently, or whether it gets
treated as solved after each retraining cycle only to resurface, is the
practical question this bet is watching.
