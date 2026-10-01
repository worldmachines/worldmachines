---
summary: 'Berinato follows the 2007 cat-and-mouse between researchers and the Gozi/76service malware-as-a-service operation (and its successors Torpig, MPACK, Prg), arguing that criminals'' distributed pain and distributed risk, together with banks'' transferred risk, make the market resilient to takedowns.'
tags:
- 'scott-berinato'
- 'cybercrime'
- 'malware-as-a-service'
- '76service-gozi'
- 'distributed-risk'
- 'transferred-risk'
- 'banks-and-fraud'
- 'russian-business-network'
last_updated: 2026-10-01
level: reading
source: 'gilman-deviant-globalization'
spans:
- 537238:564687
cites:
- 'gilman-deviant-globalization#u24-c1'
- 'gilman-deviant-globalization#u24-c2'
- 'gilman-deviant-globalization#u24-c3'
- 'gilman-deviant-globalization#u24-c4'
- 'gilman-deviant-globalization#u24-c5'
- 'gilman-deviant-globalization#u24-c6'
connects:
- 'gilman-deviant-globalization-ch13-berinato-hacker-economy-1'
- 'decentralization-produces-chokepoints'
---

# Gozi, Torpig and MPACK: why takedowns do not end the hacker service economy

*Chapter by Scott Berinato (first published in CSO Security and Risk, 2007), reprinted in Gilman, Goldhammer & Weber (eds.), Deviant Globalization (2011).*

This is the second half of Berinato's month-by-month account of the Gozi Trojan and the 76service.com subscription service that sold access to infected machines and the data they grabbed. Working largely from SecureWorks researcher Don Jackson's undercover access, Berinato reports a March containment effort (FBI, ISPs, antivirus vendors) that appears to shut the service down around March 12, then a rapid resurgence: a fire sale of stolen data, a more targeted form-grabber (Torpig), a 'spring edition' of Gozi on a Hong Kong server, an April focus on the iFrame distribution mechanism, a May re-emergence and collapse of the 76/Exoric partnership, and a June in which MPACK, an exploit-kit package, and a new Prg variant suggest the market is maturing. In between, Berinato offers two analytic frames, 'distributed pain with concentrated gain' plus distributed risk on the criminal side, and 'transferred risk' on the bank side. Much of the evidence is Jackson's and other security professionals' own account; Berinato notes that the FBI and Secret Service declined to comment or would not discuss the case specifically, and several claims (RBN links, who is 57 or sash) are the researchers' inferences.

## Themes

**Distributed pain, concentrated gain.** Berinato presents (via Jim Maloney, a former Amazon CSO) the economic logic of the trade: skimming small sums from thousands of victims yields a large gain that no single victim or bank cares enough to chase, and law enforcement cannot justify resources unless it can aggregate many victims into one big case. The point is the author's synthesis of security-industry voices, not a measured statistic.

**Distributed risk as a supply chain.** 76 barely handles stolen data, contracts out distribution, and sells to buyers who resell to still others who cash out. Berinato argues this stratified structure mirrors the drug-cartel model, so that disrupting middlemen does not solve the problem because others arise to fill the void (his example: Smash founding the IAACA after ShadowCrew was taken down). The business is modular and outsourced, with iFramebiz-style distribution services, MPACK sold on a customer-service model, and development kits that let buyers adapt code to evade antivirus.

**Transferred risk on the defender side.** Banks, in Berinato's account, meet regulation well enough to pass audits, then write the fraud off as acceptable loss and, in Jackson's prediction, will shift more of the burden to customers through lower fraud limits and terms of use. Bank-side voices (FS-ISAC's Bill Nelson, Hoff) push back that customers demand online banking and value convenience over security; Berinato says it is hard to tell who is right since most banks decline to talk. This is an argument about incentives, with the banks' own view only thinly represented.

**Resilience through adaptation; the 'infected endpoint' conclusion.** Each takedown produces a new variant, server, or ISP, 'two sides entwined in an endless, uneasy foxtrot.' 76service, Jackson says, failed for lack of manpower (it could not scale), not because the service model was flawed. Chris Rouland of IBM ISS draws the radical conclusion that security strategy must assume 'infected end points' and work out how to secure a transaction on an infected machine. Berinato closes with the expectation that criminals are becoming architects rather than engineers, operating with 'de facto immunity'.

**Fit with the volume and with World Machines.** The chapter fits the editors' picture of deviant networks running on mainstream infrastructure (browsers, banks, ISPs, iFrames) and exploiting the gap between what is cheap to attack and costly to police. It also resonates, only partly, with [[farrell-underground-empire]] and [[weaponized-interdependence]], which read the same network chokepoints from the state side: here the chokepoints are mostly not seized by any state, and Berinato is a trade journalist, not a theorist. The criminals' modular supply chains and the difficulty of aggregating distributed harm into something legible to enforcement loosely echo [[Legibility]], though Berinato does not use that frame.

## Notable passages

**Distributed pain/concentrated gain (c1).** Maloney's arithmetic of skimming $10 from 10,000 cards, with each bank writing off its share, and the law-enforcement aggregation problem.

**Distributed risk and the cartel analogy (c2).** The supply-chain structure of credential dealing, the Goodfellas aside about newbies who 'concentrate the pain', and the claim that removing middlemen only invites replacements.

**Transferred risk (c3).** Regulation, audits, acceptable-loss budgets and insurance, set against banks pushing online banking while pushing problems away; consumers' apathy and the banks' silence.

**Banks will shift more risk to customers; Rouland's 'give up' (c4).** Jackson's prediction on fraud limits and terms of use, Rouland's disagreement, and the 'infected end points' strategy.

**Why 76service failed and will return (c5).** Jackson's view that the failure was one of manpower and scale, not the service model, with Torpig seen as the next step.

**MPACK as solution, not product (c6).** James's 'architects instead of engineers' remark, the packaging of exploits, iFrames and malware with customer service, and the Briz example of defenders' countermeasures being absorbed as market conditions.

The unit also reports (briefly and without need for detail) Torpig's targeting of bank URLs and mimicry of normal transactions, the March 12 fire sale in which accounts made transfers up to $49,000 to stay under fraud limits, Exoric's own project and GucciService storefront, the May Gozi variant with anti-researcher features, and mid-June reports of Brazilian and Prg Trojans that alter transactions or ship with development kits.
