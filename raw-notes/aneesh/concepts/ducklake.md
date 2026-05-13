---
summary: "An open lakehouse format from the DuckDB team that stores metadata in a SQL database and data in Parquet, designed to be simpler and more portable than Iceberg or Delta Lake."
tags: [data-engineering, duckdb, open-source, parquet, lakehouse, biotech, open-formats]
last_updated: 2026-04-09
---

# DuckLake

DuckLake is an open lakehouse format developed by the [[DuckDB]] team (as of 2025, still approaching production readiness). It is a design inversion relative to [[Apache Iceberg]] and [[Delta Lake]].

## Design Inversion

| | Iceberg / Delta | DuckLake |
|---|---|---|
| **Metadata location** | Scattered JSON/Avro manifests in object storage | Single SQL database |
| **Data location** | Parquet on blob storage | Parquet on blob storage (same) |
| **Catalog dependency** | Separate catalog service required | SQL DB serves as catalog |
| **Cross-table transactions** | Advanced/complex feature | Native, simple |

The key insight: metadata is small and benefits from relational structure; data is large and benefits from cheap object storage. DuckLake separates these concerns cleanly.

## Catalog Backends

The SQL metadata catalog can be backed by:
- **Postgres** — for production, multi-user environments
- **MySQL** — similar
- **MotherDuck** — for cloud-managed DuckDB
- **DuckDB itself** — for single-user/local development

## Progressive Scaling

DuckDB + DuckLake runs on a laptop. The same codebase, pointed at MinIO-on-prem or S3, scales to petabytes. This "start tiny, scale fast" property is unusually important in research settings where data volumes are unknown at project start.

## No Vendor Lock-In

Operations are defined as plain SQL. Any SQL-compatible engine can read or write a DuckLake. This contrasts with Databricks' Delta Lake, which has commercial extensions that create switching costs.

## Status (as of 2025)

Not yet production-ready, but the team has a strong track record (DuckDB itself is well-regarded for reliability). Recommended for new biotech projects that can afford to be early adopters.

## Cross-References

- [[Data Lakehouse]] — the broader architectural concept
- [[DuckDB]] — the engine and team behind DuckLake
- [[Open Data Formats]] — the vendor lock-in argument
- [[Scientific Reproducibility]] — time-travel and ACID guarantees
- [[Why Every Biotech Research Group Needs a Data Lakehouse]] — source essay
