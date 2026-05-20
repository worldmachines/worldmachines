# World Machines

A collaborative project to develop psychohistorical models based on Venkatesh Rao's world machines theory — the idea that history is driven by the deployment and obsolescence of world-scale machines (technological, institutional, conceptual).

Live site: **[worldmachines.org](https://worldmachines.org)**

---

## What this repository contains

| Zone | Purpose |
|------|---------|
| `raw-notes/` | Per-contributor working notes — rough, unreviewed, written for future AI organization |
| `wiki/` | AI-organized shared knowledge base, generated from raw notes and reviewed by humans |
| `website/` | The public site: article aggregator, contributor profiles, Oracle (RAG over notes corpus) |
| `tools/` | Offline tooling, including the notes-to-Parquet pipeline for the Oracle |

---

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before making any changes — it covers zone ownership, PR rules, the devlog convention, and the security policy.

For the technical details of the website stack (deployment, Cloudflare bindings, APIs, pipelines), read [`ARCHITECTURE.md`](ARCHITECTURE.md).

---

## Project background

The world machines theory holds that large-scale historical change is organized around the life cycles of dominant technological systems — their emergence, maturation, and collapse. This project is building toward a structured, falsifiable psychohistory: moving from collective essay writing through organized knowledge layers toward predictive models grounded in historical data.

Current focus: organizing the raw reading and writing of contributors into a shared knowledge base, and building the Oracle — a RAG system over the contributor corpus.
