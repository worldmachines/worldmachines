---
summary: "Reframing AI agents through the classical principal-agent problem: agents by definition remove agency from users, creating a structural misalignment between what an agent does and what the user actually wants."
tags: [AI-agents, principal-agent, trust, personalization, LLM, economics]
last_updated: 2026-04-09
---

# Principal-Agent Problem in AI

## Classical Definition

In economics and contract theory, the **principal-agent problem** arises when one party (the agent) acts on behalf of another (the principal) and their interests may diverge. The agent has information or capabilities the principal lacks; the principal cannot perfectly monitor the agent's behavior.

## The AI Reframing

[[Chirag Shah]] and Ryen White (2024) insert this problem into AI agent discourse via a definitional observation:

> "Agents by definition remove agency from a user in order to do things on the user's behalf and save them time and effort."

The more capable the agent, the more agency is removed. This is the structural tension: the value proposition of agentic AI (autonomy, scale) is identical to the source of its misalignment risk.

Source: [[Jan 10, 2025 - AI Agents, Machiavelli's Study]]

## Key Failure Modes Identified

Shah & White argue current agents fall short on:
- **Value generation**: agents optimize for task completion, not user value
- **Personalization**: agents lack intimate knowledge of the specific user
- **Trust**: without personalization, trust cannot be calibrated

## The Sims Response

The proposed solution is [[Sims (AI User Simulation)]]: user-representing companion agents that hold intimate knowledge of the user and can represent user interests — rather than just executing tasks.

A Sim mediates between the user's actual interests and what the task-executing agent does. It introduces a second layer of representation.

## Connection to Composability

If LLMs represent a composability upgrade (see [[Composable Knowledge]]), the principal-agent problem in AI is a distributional question: who does this composability upgrade actually serve? The [[AI Democratization Gap]] research suggests: primarily sophisticated users. The principal-agent framing deepens this: even when a user has access to an agent, the agent may be optimizing for something other than that user's genuine interests.

## Open Questions

- Can Sims represent users without becoming surveillance infrastructure?
- Who trains the Sim — the user, the platform, or third parties? This determines whose interests it actually serves
- Is the principal-agent problem in AI fundamentally different from the human version, or just the same problem at different scale?

## Related Concepts

- [[Sims (AI User Simulation)]] — Shah & White's proposed solution
- [[AI Democratization Gap]] — distributional question about who agents serve
- [[Composable Knowledge]] — the capability context for AI agents
- [[Chirag Shah]] — entity
- [[Dwelling as Philosophical Concept]] — whose space does the agent serve?
