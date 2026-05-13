---
summary: "The distinction between AI that eliminates tedious execution (tool) and AI that guides judgment and strategy (advisor) — and the argument that current AI systems are suited for the former but not the latter."
tags: [ai-applications, expertise, judgment, llm-limitations, healthcare-ai]
last_updated: 2026-04-09
---

# AI as Tool vs. Advisor

## The Distinction

Sathe (see [[On Being Good vs. Knowing Good]]) draws a clean line:
- **Tool**: Automates tedious execution. Eliminates rote work while preserving human judgment about what to do with the output. The spreadsheet analogy: it doesn't tell you what to analyze, it does the arithmetic once you know what you want.
- **Advisor**: Guides strategy and judgment under uncertainty. Knows which option is better when options are ambiguous. Pushes back on the stated goal when the goal is wrong. Speaks confidently in uncertainty, drawing on experience.

The claim: LLMs are excellent tools, poor advisors.

## Why the Distinction Matters

Advisors require [[Taste as Epistemic Capacity]] — the experience-grounded capacity to make good judgments. This is not an AI capability gap to be closed by better training; it is a structural consequence of training on text rather than acting in the world.

In practice:
- **Good AI tool use**: ISO template documents, drafting reference letters, generating code scaffolding, summarizing papers
- **Bad AI advisor use**: strategic guidance, risk assessment, ethical judgment, medical diagnosis without human oversight

The failure mode of treating tools as advisors: you apply the LLM's output without applying your own judgment, and discover later that the output was confidently wrong (see [[Hallucination]]).

## The Healthcare Stakes

[[Mission-Critical AI]] is where the distinction has the highest stakes. Sathe envisions "doctors who integrate AI into their workflows with enthusiasm yet maintain high standards" — AI as tool that accelerates clinical work, human expert as the advisor whose judgment governs treatment decisions. See also [[AI Agents in Healthcare]].

## Related Concepts

- [[Taste as Epistemic Capacity]] — what advisors have and tools don't
- [[Expertise]] — the faculty the distinction depends on
- [[Mission-Critical AI]] — where mistaking tool for advisor causes harm
- [[Composite AI Architecture (Experts + LLM + KG)]] — the architecture that preserves human advisory role
