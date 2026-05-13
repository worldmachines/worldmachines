---
summary: "The principle that scientific and research data should be stored in open, portable formats to avoid vendor lock-in and ensure long-term reproducibility."
tags: [data, open-source, reproducibility, vendor-lock-in, parquet, biotech, science]
last_updated: 2026-04-09
---

# Open Data Formats

The principle: scientific data should be stored in formats that are readable by any tool, not just the proprietary system used to create it.

## Why It Matters in Research

- **Longevity**: commercial software may be discontinued, change pricing, or be acquired. Data in proprietary formats becomes inaccessible.
- **Reproducibility**: any researcher should be able to reproduce an analysis without a specific vendor's license.
- **Collaboration**: open formats reduce friction when working across institutions or tools.
- **Exit costs**: proprietary formats create switching costs that give vendors leverage over customers.

## Key Open Formats

| Format | Use Case |
|---|---|
| **Parquet** | Columnar analytics data; used by Iceberg, Delta, DuckLake |
| **FASTQ** | Raw DNA/RNA sequencing reads |
| **TIFF** | Microscopy images |
| **CSV** | Simple tabular data |
| **HDF5** | Large numerical arrays (common in single-cell) |

## The Lakehouse Context

[[Data Lakehouse]] architectures built on open table formats ([[Apache Iceberg]], [[Delta Lake]], [[DuckLake]]) keep the underlying Parquet files portable. Even if you stop using the lakehouse layer, your data is still readable.

This is contrasted with proprietary formats used by Databricks, Snowflake, or other vendors where data is stored in formats that tie you to their platform.

## Epistemic Connection

Open data formats connect to a broader [[Scientific Reproducibility]] ethic: science depends on the ability of others to verify and extend your work. If your data is locked in a proprietary format, the foundational act of sharing is compromised.

## Cross-References

- [[Data Lakehouse]]
- [[DuckLake]]
- [[Scientific Reproducibility]]
- [[Biotech Data Management]]
- [[Why Every Biotech Research Group Needs a Data Lakehouse]]
