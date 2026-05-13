---
summary: "A data architecture pattern that combines the cheap, schema-agnostic storage of a data lake with the ACID guarantees, governance, and query performance of a data warehouse."
tags: [data-engineering, architecture, data-lake, data-warehouse, biotech, open-formats, ACID]
last_updated: 2026-04-09
---

# Data Lakehouse

A data lakehouse is a unified data architecture that merges:

- **Data lake**: cheap, schema-agnostic storage (typically object storage like S3 or MinIO); stores raw files in any format (TIFF, FASTQ, CSV, Parquet, PDF).
- **Data warehouse**: ACID transactions, structured query support, governance, access control, time-travel queries.

## Why the Hybrid

Traditional approaches force a choice:
- Raw files in folders: cheap, but no queryability, no lineage, no governance.
- SQL warehouse: queryable and governed, but expensive, schema-rigid, and forces data into one format.

A lakehouse keeps data in open formats on cheap storage while adding a catalog layer that provides transactional guarantees and query capability.

## Key Capabilities

| Capability | Why It Matters in Biotech |
|---|---|
| **Native multimodal storage** | Keep TIFF stacks, FASTQ, Parquet side-by-side |
| **Column-level lineage** | Trace any value back to its source for FDA/EMA audits |
| **Time-travel** | Reproduce analysis as of a specific date for GLP compliance |
| **In-place analytics** | Push DuckDB/Spark compute to the data; no ETL movement |
| **Open formats** | Exit any vendor; Parquet files are readable by any engine |

## Open Table Formats

The lakehouse pattern requires an open table format to provide the catalog layer:

- **[[Apache Iceberg]]**: widely adopted; scatters JSON manifests across object storage.
- **[[Delta Lake]]**: Databricks-originated; similar approach.
- **[[DuckLake]]**: newest entrant; stores all metadata in a SQL database, simpler design.

## Biotech-Specific Value

See [[Why Every Biotech Research Group Needs a Data Lakehouse]]. The case is especially strong in biotech because:
1. Data types are maximally heterogeneous (images, sequences, tabular assay data, PDFs).
2. Regulatory compliance requires reproducibility and lineage.
3. Research teams are small and cannot afford dedicated data engineering headcount.
4. ML/AI workflows require moving data and compute together.

## Cross-References

- [[DuckLake]] — the specific implementation recommended for biotech
- [[Scientific Reproducibility]] — time-travel and lineage serve this goal
- [[Open Data Formats]] — vendor lock-in prevention
- [[Biotech Data Management]]
- [[Why Every Biotech Research Group Needs a Data Lakehouse]] — source essay
