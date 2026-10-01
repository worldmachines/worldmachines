---
summary: 'Berinato traces the lineage of form-grabbing Trojans from Berbew to Gozi and, through security researcher Don Jackson''s January-February 2007 discovery of 76service.com, argues that Internet crime is shifting from software attacks to a subscription-based service economy that banks, merchants and police are largely ignoring.'
tags:
- 'cybercrime'
- 'hacker-service-economy'
- '76service'
- 'gozi-trojan'
- 'russian-business-network'
- 'identity-theft'
- 'malware-as-a-service'
- 'deviant-globalization'
- 'scott-berinato'
last_updated: 2026-10-01
level: reading
source: 'gilman-deviant-globalization'
spans:
- 519345:537238
cites:
- 'gilman-deviant-globalization#u23-c1'
- 'gilman-deviant-globalization#u23-c2'
- 'gilman-deviant-globalization#u23-c3'
- 'gilman-deviant-globalization#u23-c4'
- 'gilman-deviant-globalization#u23-c5'
- 'gilman-deviant-globalization#u23-c6'
---

# Gozi, 76service and the Shift from Malware to Crime-as-a-Service

*Chapter by Scott Berinato (first published in CSO Security and Risk, 2007), reprinted in Gilman, Goldhammer & Weber (eds.), Deviant Globalization (2011).*

This is the first part of Berinato's two-part reported narrative. It opens with a genealogy of form-grabbing Trojans (Berbew, A311-Death, the Haxdoor family, Nuclear Grabber) and their reputed authors, then follows researcher Don Jackson of SecureWorks as a favour to a friend leads him to a Gozi sample, a Russian Business Network server, and a 3.3 GB file of more than 10,000 credentials from 5,200 machines. Berinato's argument, voiced partly through Jackson, is that Gozi matters not as a technical innovation but as a business model: electronic crime is moving from episodic, software-based attacks to a chronic, service-based economy. The unit ends with Jackson gaining access to 76service.com and learning how its subscription model works.

## Themes

**From product to service.** Berinato argues, citing Jackson's view, that Gozi was "no different" technically from its four-year-old ancestor Berbew; what was new was that it was sold as a service. 76service rented 30-day "projects" on Gozi-infected machines instead of selling stolen credentials, and layered on ancillary paid services (report clean-up, per-bank extracts, remote drops). The seller becomes a broker who barely handles stolen data, which Berinato presents as both safer and more scalable.

**Chronic rather than episodic crime.** Berinato compares the change to bank robbery by small gangs giving way to drug trafficking run by syndicates, and predicts a "golden age" in which hackers run less violent and more scalable syndicates, like Barbary pirates or Colombian cartels but with code. This is his own forecast, not a finding. Secure Science's Lance James supplies the scale figures (3 million compromised credentials and 250,000 stolen cards a month).

**Financial-market logic inside the underground.** Subscribers hold a portfolio of infected machines to spread risk, as fund managers do, and price is tied to freshness ("fresh bots" from $1,000 per machine per project, per Jackson) and to the richness of the identity captured (a card number worth about $5 rises to hundreds of dollars with billing data, up to a full financial identity). Berinato's analogy of grafting plants also frames malware evolution as modular recombination of code.

**Institutional apathy and weak governance.** Berinato claims that banks, merchants and consumers have accepted online crime as acceptable loss (a "conspiracy of apathy"), that police lack resources and jurisdiction, and that some security firms are giving up on securing machines. He also observes that the boutique security-research industry profits from the problem, since research is a marketing tool and larger firms are acquiring these companies: "a sign of how much money can be made trying to catch up". These are Berinato's assertions plus quotes from anonymous researchers and Chris Hoff, not systematically evidenced.

**Fit with the volume.** The chapter illustrates the editors' theme of deviant entrepreneurs using ordinary commercial infrastructure and ordinary market forms (e-commerce, subscriptions, customer service, billing cycles) for illicit ends, with the state largely absent. It loosely echoes [[farrell-underground-empire]]'s theme of networked infrastructure, though Berinato says nothing about state chokepoints. It also resonates, in a half-fitting way, with [[illegibility-as-elite-defense]]: the criminals operate from permissive hosting (RBN) and unprosecuted jurisdictions, though Berinato does not frame this in legibility terms. Berinato is a technology journalist, and attributions to the HangUp Team, Smash and Corpse are expressly beliefs ("believed to be", "many believe").

## Notable passages

The passage naming the shift from software to service and from episodic to chronic crime is the thesis. The 76service passages (30-day projects, the portfolio analogy, the value of a full identity) give the mechanism and pricing. The "conspiracy of apathy" paragraph carries Berinato's governance claim and golden-age forecast.
