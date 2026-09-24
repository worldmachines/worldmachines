---
summary: "Across six independent escape attempts documented in Underground Empire — the Eurodollar market, the anti-MARTI revolt that created SWIFT, Baran's distributed network, the fabless/foundry split, INSTEX and CIPS, and Ethereum — every effort to route around a centre either produced a new chokepoint or failed, and the notes together separate two distinct failure modes that no single chapter states."
tags: [chokepoints, capture-resistance, decentralization, network-effects, infrastructure, weaponized-interdependence, world-machines]
last_updated: 2026-09-23
level: canon
sources: [farrell-underground-empire-ch01-wriston-world, farrell-underground-empire-ch02-stormbrew-map, farrell-underground-empire-ch03-war-without-gunsmoke, farrell-underground-empire-ch04-waking-into-winter, farrell-underground-empire-ch05-hooks-captain]
---

# Decentralization Produces Chokepoints

[[farrell-underground-empire]] contains six serious, well-resourced, independently motivated attempts to escape a centre. Each chapter tells its own as a local story. Read across the notes, they turn out to be one story told six times — and the repetition supports a claim none of the individual chapters makes: **an attempt to route around a chokepoint reliably produces a new chokepoint, and the reason it does is that the escape is designed at one layer while capture happens at the layer beneath it.**

## The six cases

| Escape attempt | Motive | What it produced |
|---|---|---|
| Eurodollar market | Dollar demand abroad, rate caps at home | A "legal gray zone" whose every dollar was still backed by "a real dollar," sitting in a U.S. bank |
| The anti-MARTI revolt | Refusing Citibank's proprietary standard | SWIFT — an obligatory passage point for all global finance |
| Baran's distributed network | Surviving nuclear decapitation | Ashburn, Virginia: a "vast parabolic mirror, concentrating the Internet into a tiny point" |
| The fabless/foundry split | Efficiency through specialisation | TSMC as "a single point of failure for the U.S. economy"; U.S. design IP as the matching lever |
| INSTEX and CIPS | Sovereign escape from the dollar | One completed transaction; a fraction of SWIFT's volume |
| Ethereum and DeFi | Statelessness engineered into code | Coinbase, MetaMask, Alchemy, Infura; DAO voting concentrated in venture funds |

## Two distinct failure modes

The chapters are usually read as making a single ironic point about decentralisation. Placed side by side, they actually separate into two mechanisms with different structures — and the distinction matters for anyone trying to build something that resists capture.

**Anti-peer designs that succeed at their stated goal and lose at the layer below.** SWIFT and Ethereum are the pure cases, and they are structurally identical despite forty years and an ideological universe between them. SWIFT was built specifically so that no single bank could do what Citibank tried to do with MARTI, and it worked: no bank captured SWIFT. It was captured instead by the state whose currency and banks underwrote the clearing system the whole cooperative depended on — its board folded not because a subpoena was irresistible but because its members needed continued U.S. financial access. Ethereum was built so that no single intermediary could gatekeep, and Vitalik Buterin warned explicitly about "base layer services" concentrating power. When OFAC designated Tornado Cash, most crypto intermediaries capitulated instantly. In both cases the design successfully anticipated capture by a competitor and failed to anticipate capture through the settlement layer, which nobody was defending because nobody had built it.

**Sovereign alternatives that fail for want of will or scale.** INSTEX and CIPS are the other kind. These were not naive about state power — they were built by states, specifically to escape another state's leverage. They failed anyway. INSTEX completed one transaction and did essentially nothing because the EU was "unwilling to take the transformative steps" a real alternative required; the notes describe it frankly as a face-saving "laboratory" for "weird things." CIPS moves a fraction of SWIFT's volume. The obstacle here is not architectural blindness but the cost of building an alternative attractor from zero against an incumbent already carrying everyone's traffic.

The first failure mode is a design error and in principle correctable. The second is a [[constructal-law]] problem — the incumbent carrier minimises resistance to flow for every existing participant, so the challenger must pay the full cost of the network while offering less of it. This is why Europe's discovery in 2022 reads the way it does: "the more that the EU sought to build its own sources of power and authority, the more it realized that it needed what the United States had." Escape and dependency increased together.

## Why the pattern recurs

Three mechanisms appear in every case.

**Someone's unit of account is the floor.** Offshore dollars are still dollars. A messaging cooperative still settles in a currency someone issues. A stablecoin still redeems somewhere. The escape is horizontal; the capture is vertical.

**Stickiness compounds.** Ashburn is the clearest physical instance: colocation, buried fiber, and cross-connects meant that in the corridor "more server farms attracted more high-speed fiber, which in turn attracted more server farms, in a self-reinforcing loop." The same dynamic in software is called network effects; in the [[world-machines]] vocabulary it is a [[gravitational-attractor]] accreting mass, and the asymmetry is the point — the attractor bends the field of action for everyone routing through it whether or not they consent to or even perceive it.

**Specialisation manufactures single points.** The fabless/foundry split was celebrated by the industry as "a beautiful and extraordinarily complex global ecology" beyond any single country's control — sixteen thousand suppliers worldwide. What it actually produced was two chokepoints instead of one, pointed at each other: fabrication concentrated at TSMC ninety miles from a strategic rival, design IP concentrated in the U.S., "like a fisherman's longline with barbed and baited hooks." Distribution of *activity* is not distribution of *control*, and the two were consistently confused by the people doing the distributing.

## What this does to capture resistance

[[capture-resistance]] is defined in this wiki as a property of liveness — resisting instrumentalisation by external agents. The value of these six cases is that they are the closest thing available to a controlled experiment on whether that property can be *engineered into infrastructure* rather than merely asserted as a posture. The verdict is discouraging but precise: of the six, exactly one thing in the book proved genuinely resistant — code with no possible off-switch, Tornado Cash itself, which had no intermediary to coerce. Everything else had a human institution somewhere in the stack whose commercial dependency could be leveraged.

That suggests a sharp criterion. Capture resistance survives contact with a sovereign only where there is no party with something to lose. Every diplomatic version of neutrality — Microsoft's "Digital Geneva Convention," Morris Chang building TSMC as an even-handed "Switzerland of semiconductors" — decayed the moment a great power needed to test it, because the neutral party always had assets, employees, market access, or a fab. Neutrality is not a structural property; it is a standing offer that lapses when someone declines it.

The uncomfortable corollary, which the book states without quite endorsing: the only fully capture-resistant infrastructure is infrastructure nobody is responsible for — which is also infrastructure nobody can fix, govern, or hold accountable. That is not obviously a better world, and the confrontation between sovereign authority and "alegal" mathematics is left unresolved.

## Related

- [[farrell-underground-empire]]
- [[weaponized-interdependence]]
- [[walter-wriston]]
- [[capture-resistance]]
- [[gravitational-attractor]]
- [[constructal-law]]
- [[infrastructure-inheritance]]
- [[infrastructure-as-political]]
- [[protocol-gods-and-platform-demons]]
