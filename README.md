# Data Pipeline: Technological Trend Mining

This repository implements an automated data mining pipeline designed to extract, analyze, and forecast **technology development trends** from large-scale bibliographic and scholarly databases. 

Rather than a generic literature search, this pipeline is highly opinionated. It filters for **high-impact, authoritative research** and dynamically aligns the knowledge discovery process with specific, user-defined research vectors (e.g., Multi-Agent Systems, MLOps, Distributed Architecture).

## Core Objectives

* **Targeted Trend Analysis:** Mine citation graphs and textual metadata to identify rising technologies, paradigm shifts, and decaying methodologies over time.
* **Impact & Authority Filtering:** Cut through the noise by prioritizing literature based on "citation velocity," influential citation metrics, and the historical authority of authors/venues.
* **Strict Semantic Alignment:** Ensure the mined trends are deeply relevant to specific technical directions by utilizing vector embeddings and semantic similarity scores against target prompts.
* **Insight Synthesis:** Automatically generate temporal trend reports, concept heatmaps, and highlight the "frontier" papers driving current technological shifts.

## Data Sources

| Source | Role in Pipeline |
| :--- | :--- |
| **Semantic Scholar (S2AG)** | High-signal filtering using "influential citation" flags and citation intent. |
| **OpenAlex** | Comprehensive graph for tracking the temporal growth of specific tech concepts. |
| **arXiv (OAI-PMH)** | The primary source for bleeding-edge preprints in CS, AI, and Systems. |
| **DBLP** | Verified metadata for top-tier computer science conferences and journals. |

## Pipeline Architecture

```text
[1. Targeted Ingestion]
      │ Fetch recent literature matching seed concepts from OpenAlex/arXiv/DBLP
      ▼
[2. Impact & Semantic Pruning]
      │ ├── Alignment Check: Vector similarity against target domain vectors
      │ └── Authority Check: Filter by venue tier, author impact, citation velocity
      ▼
[3. Temporal Trend Mining]
      │ ├── Entity Extraction (NLP): Identify novel architectures, frameworks, algorithms
      │ └── Time-Series Analysis: Track Year-over-Year growth of extracted entities
      ▼
[4. Trend Digest & Output]
      └── Curated report of trending technologies + the foundational papers driving them