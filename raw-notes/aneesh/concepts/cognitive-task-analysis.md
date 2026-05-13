---
summary: "A set of methodologies originally developed for US military training to extract tacit expert knowledge — how skilled practitioners actually make decisions — into explicit, transmissible form."
tags: [expertise, knowledge-extraction, military, training, cognitive-science]
last_updated: 2026-04-09
---

# Cognitive Task Analysis

## Definition

Cognitive Task Analysis (CTA) is a family of methodologies developed primarily in military training contexts to extract the tacit, procedural knowledge of highly skilled experts — the judgment calls, pattern recognition, and heuristics that practitioners cannot easily articulate but that distinguish expert from novice performance.

Standard task analysis captures *what* someone does. CTA captures *how* they think while doing it: what cues they attend to, what decision points they navigate, what alternatives they considered and discarded.

## Relevance to the Composite AI Architecture

Sathe (see [[Dancing on the Shoulders of Giants]]) mentions CTA as a practical tool for extracting the tacit expert knowledge that would populate [[Knowledge Graphs]]. The cold-start problem for knowledge graphs in high-stakes domains is that the most valuable knowledge is precisely the kind that experts struggle to articulate. CTA provides methods for surfacing it.

In the [[Composite AI Architecture (Experts + LLM + KG)]] framing, CTA is the extraction pipeline: it converts [[Muddling Through]] heuristics and expert judgment into explicit, structured knowledge that can be encoded in a KG and thus made accessible to LLM-mediated traversal.

## Connection to Knowledge Diffusion

CTA represents a formalization of what happens informally when expertise is transmitted between practitioners — but faster, more complete, and institutional rather than personal. In [[Wright's Law]] terms, CTA is a mechanism for accelerating the diffusion step that currently requires a generational delay in healthcare.

## Open Questions

- CTA methods are time-intensive and contested — there is no single agreed protocol
- Expert knowledge elicited under CTA conditions may not reflect actual expert practice (social desirability, verbalization effects)
- Whether CTA-extracted knowledge is sufficiently structured to encode in KG form without significant loss is an empirical question

## Related Concepts

- [[Expertise]] — what CTA attempts to extract
- [[Knowledge Graphs]] — where extracted knowledge gets encoded
- [[Muddling Through]] — the frontier decision-making style CTA tries to capture
- [[Composite AI Architecture (Experts + LLM + KG)]] — the deployment context
- [[Wright's Law]] — the efficiency goal that CTA-fed KGs serve
