---
summary: 'Shared coordination has been assumed to require a shared tempo, but computation can translate between temporal systems instead of unifying them — one instant can be rendered into several lived temporal positions at once, which means plurality and coordination are not actually in tension.'
aliases:
- 'Coordination does not require temporal uniformity'
tags:
- world-machines
- divergence-machine
- time
- coordination
last_updated: 2026-09-14
---

# Coordination does not require temporal uniformity

## The idea

Synchronization has been the default answer to coordination for so long that the two look like the same problem. They are not. Synchronization means one shared tick that everyone reconciles to; coordination means people being able to act together. The second does not require the first. What it requires is translation, and translation is something computation is unusually good at.

The clearest working case is a solar-relative standard. Horizon Time, from Paragonday, organises time around local sunrise and sunset, and an application can convert between ordinary civil clock time and a person's position in their own daylight cycle. A meeting then happens at one shared instant while occupying three different lived positions: early daylight for one participant, the middle of the day for another, darkness for a third. The machines hold interoperability; the interface renders the common event into the temporal world each person actually inhabits. Nobody had to adopt anybody else's tempo, and the meeting still happened.

The same structure already runs underneath civil time, which is where the claim stops being speculative. Coordinated Universal Time is a negotiated compromise between atomic stability and a planet that does not rotate regularly, maintained through leap seconds since 1972. Software converts among references using Earth-orientation data. Reforming UTC would not abolish the Earth's rotation or the need for astronomical time; it would change which layer reconciles the two and how applications ask for it. Conversion is not a proposal. It is what the stack has quietly been doing all along, badly documented and mostly invisible.

The reason this matters beyond convenience: if coordination required uniformity, then every diverged temporal world would be a coordination cost, and the only way to act together would be for somebody's tempo to win. Translation breaks that trade. Plurality stops being the price of coexistence and becomes something a system can hold.

Which is exactly where the honest problem sits. A converter is never neutral. It picks reference points, defines what counts as equivalent, suppresses some differences and makes others salient. Bad conversion domesticates diverse temporalities into the dominant one while presenting the result as inclusion — everyone technically accommodated, one tempo still setting the terms, and now with an interface that makes the asymmetry harder to see than an honest imposition would have been. The useful questions are therefore about the converter itself: which differences are preserved rather than normalised, where the translation happens, whether a user can inspect and contest it, and whether it enables coexistence or merely makes one system easier to impose.

## Where it comes from

From "Time Moves Down the Stack" (Protocol Institute Symposium, 2026), where conversion is one of three proposed directions for a practice of Micro Time. The leap-second and Earth-orientation material draws on the BIPM and CGPM resolutions on UTC, ITU-R time standards, and the USNO and IERS Earth-orientation services. Isabell Otto's work on interfacing temporal plurality and the leap-second problem sits behind the framing.

## How settled this is

That the conversion machinery exists and works is not a claim, it is a description — the leap-second case is operational infrastructure, not a thought experiment. What is mine and unsettled is the generalisation: that translation is a viable *general* model of coordination rather than a trick that works for a handful of well-defined references like solar position and Earth rotation.

Those two cases are both unusually tractable. They convert between things that are physically measurable and have agreed definitions. Whether the same approach survives contact with temporal differences that are social rather than astronomical — differing senses of urgency, of how long a decision should take, of when a matter is settled — is untested here, and I would expect it to be much harder, because there is no equivalent of Earth-orientation data for those.

## Connections

- [[four-cell-coordination-grid|Who keeps the time: a four-cell coordination grid]] — Sean poses exactly this fork, synchronization against translation, and wagers that AI makes translation cheap enough to coordinate without a canonical clock; this note supplies the worked cases his wager does not have, and the failure mode it does not name
- [[three-seeds-insufficient-alone|Rewiring, conversion and attunement each fail alone and only work together]] — conversion is one of the three, and on its own it is the one most likely to make an unjust arrangement comfortable
- [[divergence-in-the-periphery|Divergence grows in peripheral fields, not in the fortified center]] — the temporal version of the same claim: the interesting coordination is happening off to the side of the standard, not at it and not against it
- [[vanishing-now|The vanishing now]] — Sean's opposing pressure: private, on-demand access to time erodes the shared present, making synchrony scarce; if he is right that the answer is protecting a few high-value synchronies, then translation is at best half an answer
- [[embedded-self-knowledge|Divergent self knowledge requires embedded, embodied, non-reproducible inquiry]] — adjacent on method: both refuse the move of standardising a situated thing in order to make it comparable

## Open

Is there any temporal difference that genuinely cannot be converted — where translation would destroy the thing being translated rather than render it? Ritual time is my suspect. A feast day rendered into somebody else's tempo as a calendar entry may have survived the conversion in exactly the sense that matters least.
