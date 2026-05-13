---
summary: "The principle that scientific analyses must be re-runnable to produce the same results, and the data infrastructure requirements this imposes."
tags: [science, reproducibility, data, compliance, biotech, open-formats, audit]
last_updated: 2026-04-09
---

# Scientific Reproducibility

Scientific reproducibility — the ability to re-run an analysis and get the same result — is a foundational epistemic norm of science. In practice, it is often violated, especially in computational biology and data-intensive research.

## The Infrastructure Problem

Reproducibility requires:
1. **Data provenance**: knowing exactly what input data was used.
2. **Code version control**: knowing exactly what code was run.
3. **Environment reproducibility**: knowing what software environment (versions, dependencies) was active.
4. **Data immutability**: ensuring the input data hasn't changed.

Most research labs handle 1 and 4 poorly. Data ends up on laptops, modified in-place, lost when people leave. A single plot on a poster may be the only evidence an experiment happened.

## The Lakehouse Solution

[[Data Lakehouse]] architectures with [[DuckLake]] address data provenance and immutability directly:

- **Time-travel queries**: "reproduce this analysis as of 2025-07-14" — exact state of all tables at that timestamp is accessible.
- **Column-level lineage**: trace any value back to the instrument file that generated it.
- **ACID guarantees**: no partial writes; every state is consistent and recoverable.

This is not just a convenience — it is a regulatory requirement for FDA, EMA, and GLP compliance in clinical and late-stage research.

## The Broader Crisis

The "reproducibility crisis" in science (especially psychology, biomedical research) is partly an infrastructure problem but also an incentive problem: journals reward novelty, not replication. Data infrastructure can solve the former; it cannot solve the latter.

## Cross-References

- [[Data Lakehouse]]
- [[DuckLake]]
- [[Open Data Formats]]
- [[Biotech Data Management]]
- [[Why Every Biotech Research Group Needs a Data Lakehouse]]
