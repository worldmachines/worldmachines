---
summary: "Five falsifiable near-term bets each follow the same pattern: today's
  proposed fix for an AI limitation (longer context, benchmark evals,
  synthetic training data, open agent protocols, human-in-the-loop review) is
  itself a near-solution whose difficulty migrates somewhere specific and
  identifiable (context rot, eval rot, model collapse, protocol capture,
  rubber-stamp oversight) rather than actually resolving."
tags: [ai, benchmarks, synthetic-data, protocols, oversight, bet-table]
last_updated: 2026-09-05
---

# Near-term bets of the Divergence Machine

## The idea

Five specific, betable claims, each following the same shape: today's
proposed fix for a real AI limitation is itself a near-solution whose
difficulty will migrate somewhere specific and identifiable, rather than a
place where the difficulty actually resolves.

Longer context windows and persistent memory are offered as the fix for a
model's forgetting, but the difficulty migrates to forgetting well -
knowing deliberately what to drop - so that context curation, not context
capacity, becomes the scarce skill; unmanaged, this shows up as context
rot, stale or conflicting context degrading long-horizon performance, which
the bet predicts becomes a standard benchmarked failure within a couple of
years, with "infinite memory" claims walked back accordingly.

Benchmark suites are used to certify that a model is reliable, but a
benchmark is itself a frozen snapshot, so the difficulty migrates to live,
dynamic evaluation - eval design becomes the scarce and valuable work, and
the failure mode is eval rot or outright Goodharting, where models optimize
against a fixed past distribution while the actual world keeps moving; the
bet is that a flagship benchmark gets shown as saturated or gamed and
retired, with "eval rot" becoming a standard term.

Training on synthetic data, once human-generated data runs out, moves the
difficulty to provenance - verified, recent, human-generated data becomes
scarce and commands a price - because the failure mode is model collapse,
the archive eating itself until the whole system converges on a degenerate
monoculture; the irony is sharp enough to name directly, since a machine
built to celebrate divergence quietly manufacturing a new convergent
monoculture is exactly the failure this whole framework exists to watch
for.

Open protocols for agent-to-agent tool use and interoperability are
proposed to enable a decentralized ecosystem, but the difficulty migrates to
protocol governance, because whichever standard wins majority adoption
quietly becomes the new center - the same invisible-center error named
elsewhere in this set, arriving specifically through the decentralization
story's own infrastructure.

A human approver in the loop is proposed as the fix for AI mistakes, but the
difficulty migrates to designing meaningful, sampled, adversarial review
rather than routine sign-off, because at volume the human reviewer simply
rubber-stamps outputs - oversight theater, a mitigation that manufactures
false assurance and is arguably worse than having no mitigation at all,
since it looks like safety without providing it.

## Where it comes from

Five rows (B1 through B5) of the same Divergence Machine bet-table, grouped
here because each is individually thinner than the nine structural errors
but shares their same "difficulty migrates, it does not resolve" logic.

## How settled this is

Five working hypotheses, each explicitly framed as a near-term, falsifiable
bet with a stated time horizon (around two years for the memory claim)
rather than as an established finding.

## Connections

- [[escapement-set-to-a-past]] - several of these bets (context rot, eval
  rot) are the direct near-term, concrete symptoms of that row's more
  general claim about AI's reliable band drifting off a moving world
- [[the-invisible-center]] - the agent-interoperability protocol bet is a
  specific, named instance of that row's general claim about coordination-
  without-a-center rebuilding an ungoverned center
- [[the-patchwork-becomes-the-machine]] - human-in-the-loop oversight
  degrading into rubber-stamp theater is one more instance of scaffolding
  meant to contain a model instead becoming an unreliable, opaque layer of
  its own

## Open

Each of the five bets carries its own falsification condition (a specific
benchmark being retired, a specific regulatory action, a named term
entering standard usage) and is meant to be checked against events over the
next several years rather than argued from theory now.
