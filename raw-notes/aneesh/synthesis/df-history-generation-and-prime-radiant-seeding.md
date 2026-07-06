---
summary: "Dwarf Fortress's world/history generation is a working generative psychohistory engine, and its pipeline — substrate-first determinism, selective agent interiority, emergent-not-scripted conflict, and a hard no-retroactive-history invariant — is a concrete template for how to seed the World Machines Prime Radiant process, with one decisive disanalogy: DF has no ground truth to be corrected against."
tags: [world-machines, prime-radiant, psychohistory, simulation, generativity, wm-cockpit, seeding]
last_updated: 2026-05-15
---

# DF History Generation and Prime Radiant Seeding

Source: Tarn Adams (Toady One), *DF Talk* transcript, episode topic "world
generation and history generation" (bay12games.com combined transcript).
Question posed: does DF's history-generation algorithm pertain to how the
[[the-world-machines-canon]] project should *seed the Prime Radiant
process* (the asymptotic, formalized forward model behind the wm-cockpit
Oracle)?

Answer: yes, sharply — DF is a working generative psychohistory engine,
and its architecture is a concrete answer to the seeding question. But it
supplies only the *generative* half; the *assimilation/correction* half
(the Second-Foundation loop) is the World Machines project's own addition
and is not borrowable from DF.

## The DF algorithm, as a pipeline with a determinism gate

1. **Parameterize & allocate** — world size, year count. Run config only.
2. **Physical substrate** — elevation → temperature (hemisphere/pole
   first, *then* elevation) → rainfall → smoothing → iterative
   river-carving → lakes. Physics before everything.
3. **Derive regions** — biomes *computed* from rainfall × temperature ×
   drainage × elevation; regions located and named. Read off the fields,
   never hand-placed.
4. **Populate creatures** from the raws (rule library) onto the substrate.
5. **Geographic-determinism gate** — civilizations cannot be seeded until
   geography exists, because the *kind* of civilization is a function of
   local resources. Geography is the precondition of history.
6. **Seed** — caves, megabeasts; civilizations dropped as ~20 sites, each
   from **10 founder pairs, not 2** — a seed-size chosen so variance
   survives ~100 generations of drift instead of collapsing.
7. **Run forward** N years. The personality/motivation model runs **only
   for agents who rise to responsibility** — selective interiority, since
   10,000 fisherdwarves cannot be modeled deeply. Conflict is *emergent
   from numeric weighing* ("+20 here, −30 here; go"), between agents and
   *within* an agent.
8. **Read histories out by importance** — every event carries an
   interest/importance scalar (originally so dwarves know what to
   engrave). "Top ten interesting non-nobles" is a ranking query over
   what actually happened, not authored narrative.
9. **Hard invariant**: never fabricate past events that did not occur in
   the run, or "you tie yourself in knots and have inconsistencies all
   through." NPC depth hangs on civilization-*remembered* simulated
   events, fleshed out progressively, never back-dated.
10. **Simulation over guiding hand** — scripted drama is explicitly
    refused; the correct response to flat output is *improve the
    simulation*, not inject events. The guiding hand is a last-resort
    hack used only to keep the game interesting.

## Six transferable seeding principles

Mapped onto the cockpit's binding invariants (model-not-prophecy;
revisability-as-intervention; Oracle now, Prime Radiant as asymptote):

1. **Substrate-first → machine-substrate determinism.** Do not seed
   forecast trajectories before the "geography" is fixed: the energy
   regime / material substrate / Dawn–Day–Dusk phase position of each
   machine. The Prime Radiant seed is not the actors — it is the
   resource-determined phase space they are dropped into. Makes
   [[machines-as-energy-regimes]] load-bearing for seeding.
2. **Derived regions, not authored regions.** DF computes biomes from
   field-intersections. The `(machine × phase × open-question)` cube *is*
   the biome map — derive typology boundaries from the canon's field
   variables, do not assert them. Empty cells = essay seeds (already in
   the ROADMAP; the DF parallel is exact).
3. **Selective interiority.** Deep modeling only for consequential
   institutions/machines; the rest stays aggregate flow. This is
   psychohistory's own resolution-floor assumption recovered from the
   engine side.
4. **Emergent, surfaced, not scripted (tightest parallel).** DF's "story"
   is the narration of a numeric decision the sim already made. The
   Radiant's forecasts should be the surfacing of the probability-flow
   weighting the model already computes — **the tolerance band is the
   +20/−30 margin made visible.** Toady's "show what's going on when that
   stuff happens" *is* the model-not-prophecy invariant.
5. **No-retroactive-history mirrors no-backfilled-forecast.** DF forbids
   fabricating the past; psychohistory forbids fabricating a certain
   future — structurally the same rule. The model may only assert what
   the process produced or flows toward. Second-Foundation correction =
   DF's "flesh out NPCs *consistent with* remembered events" — correction
   stays consistent with the record, never overwrites it.
6. **Ten pairs, not two.** Seed the forward model from enough independent
   author-reads / theory positions that variance survives the run instead
   of collapsing to one lineage. The cockpit's author-attribution layer
   (canon / one-author-read / speculation) is the "ten pairs."

## The decisive disanalogy

DF generates history *forward from a blank substrate with no ground
truth*. The World Machines model is *fitting to an already-running real
history* (1748 → 2026 → onward) where reality is the ground truth the
model must be corrected against. DF therefore supplies the
generative/seeding half and *nothing* about assimilation/correction — the
entire Second-Foundation loop is the project's own addition. DF's
determinism is also *closed* (the sim is the only world); the Radiant is
*open* (real events arrive exogenously). So geographic determinism
transfers as a **seeding heuristic, not** a claim that substrate fixes
outcomes. Use DF for how to *start* the process; do not import its
closed-world confidence into the forecast.

## Connections

- [[simulation-and-the-socratic-question]] — simulation as a way of
  asking rather than answering; DF's "improve the simulation, don't
  script it" is the generative form of the same stance.
- [[generative-complexity-as-epistemic-value]] — DF's importance-ranked
  readout is generativity made queryable.
- [[history-machines-and-distributed-complexity]] — DF as a distributed
  history-machine; the seeding gate is where complexity is licensed.
- [[world-machines-as-interim-theory]] — the no-retroactive-history rule
  is the engine-side image of "institutionalized interim struggle."
- [[the-world-machines-canon]] — target framework for the seeding.

## Essay seed

*"Ten Pairs, Not Two: How to Seed a History"* — a piece on the
generative-engine discipline (substrate-first, selective interiority,
emergent-not-scripted, no retroactive fabrication) as a general method
for any forward civilizational model, using DF as the worked example and
the Prime Radiant as the open-world limit case where the discipline
half-applies.
