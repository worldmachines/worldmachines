---
summary: 'Nobody becomes fast enough to react inside a 350-microsecond market window, so human agency has to appear earlier and elsewhere — in negotiating, contesting and authorising the rule that acts inside the interval on your behalf, which is the only form of participation a machine-speed decision leaves available.'
aliases:
- 'Rules authored in advance are the only human agency available inside machine intervals'
tags:
- world-machines
- divergence-machine
- infrastructure
- time
last_updated: 2026-09-14
---

# Rules authored in advance are the only human agency available inside machine intervals

## The idea

Some intervals are too short for a human to act inside them, and no amount of training closes that gap — a physiological fact, not a discipline failure. The interesting question isn't how to become fast enough. It's where human agency goes once speed is ruled out.

IEX's options-market design is the clean case. Incoming messages face a 350-microsecond delay, paired with a mechanism that can update or cancel a market-maker's quotes when a rapid move would otherwise leave them stale and exploitable. No participant becomes able to react within 350 microseconds. What changes is who acts inside that window: not a trader, but a rule, authored in advance by people who could take their time over it — designing the mechanism, contesting its terms, authorising it to operate at a speed none of them could match. The rule is the delegate. Human agency shows up earlier in the sequence and at a different layer than the decision it governs.

That relocation is the content of rewiring: collectively changing the rules that operate at the point where a temporal decision gets fixed, instead of trying to occupy that point yourself. It accepts that some intervals are permanently beyond direct reach, and asks a different question of them — not *how do I act in time* but *who is authorized to write the rule that acts in time, and can that authorization be inspected and revised*.

Two things follow from taking the mechanism seriously. First, rewiring only ever protects whoever the rule is written to protect: IEX's delay directly protects participating market makers, and broader benefits to ordinary investors are an intended downstream effect, not something the mechanism itself proves. Asking *who* the rule protects does as much work as asking whether it exists. Second, the same institutional distance that makes rewiring possible is what makes it fail in familiar ways — a rule can privilege whoever was already positioned to comply, can shift the exploit elsewhere rather than close it, or can pass as protection while doing none, regulatory theater existing to have been passed rather than to act. None of this is a failure of the concept; it's what happens when the institution writing the rule is weak, captured, or misaligned with its own stated protection.

The working questions this leaves are specific enough to run on an actual system: where is the decisive interval, which rule governs it, who is authorized to alter that rule, whose possibilities does the change protect or foreclose, and how can effects be audited after the fact rather than only argued about in advance.

## Where it comes from

From "Time Moves Down the Stack" (Protocol Institute Symposium, 2026), where rewiring is the first of three proposed directions for a practice of Micro Time. The IEX case draws on the exchange's options-market design and SEC Release No. 34-103998.

## How settled this is

That IEX's mechanism exists and protects the participants it's designed to protect is public record. That it makes the broader market fairer is not established — an intended effect, argued for, not demonstrated by regulatory approval, and I have not gone further than the talk did in trying to settle it.

The general claim — authoring a rule in advance is the available agency once direct reaction is ruled out — describes what IEX and similar mechanisms actually do, and I trust it that far. Whether it generalizes into a reliable practice, rather than remaining one well-documented case plus a family resemblance to circuit breakers and grid protection, is untested here.

## Connections

- [[three-seeds-insufficient-alone|Rewiring, conversion and attunement each fail alone and only work together]] — the note this one completes, supplying the working case for what that note describes at a level of generality
- [[coordination-without-uniformity|Coordination does not require temporal uniformity]] — the sibling seed: conversion translates between temporal worlds without touching the rule, rewiring changes the rule itself, and the two fail in opposite directions alone
- [[appeal-foreclosure|Appeal-foreclosure]] — Sean's test for whether a lever still exists to petition a system; a rewired rule is a lever built on purpose, and his three questions audit whether it stayed alive or fossilized into the thing it was meant to hold accountable
- [[ornament-as-diagnostic|It takes connoisseurship for ornamental baggage to identify dead frameworks]] — the check to run on a rewiring effort well after the fact: regulatory theater is exactly this diagnostic's target
- [[descent-chain|The descent chain: how AI becomes New Nature]] — Sean's step 4 names competition sealing off every place to appeal as what completes a descent; rewiring is the attempt to hold a place open against exactly that pressure

## Open

Whether authorization itself can decay the way the decay-sequence cluster describes — a rule passing from genuinely contested to performatively ratified to ornamental compliance nobody remembers arguing about. If it can, the diagnostic above isn't a borrowed analogy; it's the maintenance check a live rewiring practice needs to run on itself, and nobody has specified who runs it or how often.
