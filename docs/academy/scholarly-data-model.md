# Scholarly Data Engineering Academy: Foundations of Canonical Bibliographic Systems

---

## 1. Problem Definition

### 1.1 Context and Challenge
Modern computational research on scientific evolution—such as technological trend mining, citation dynamics, and paradigm shift detection—requires aggregating bibliographic metadata across disparate scholarly data providers. A trend mining engine cannot rely on a single siloed repository; it must combine the real-time preprint velocity of **arXiv**, the open academic graph topology of **OpenAlex**, the authoritative publisher registry of **Crossref**, and the rich citation intents and impact indicators of **Semantic Scholar (S2AG)**.

However, scholarly data engineering is plagued by deep structural heterogeneity:
* **Decentralized Publication Lifecycle**: A scientific contribution begins as an unreviewed preprint, evolves through multiple preprint revisions, undergoes peer review, gets published in a conference or journal with a digital object identifier (DOI), and may subsequently be re-indexed or retracted.
* **Semantic Divergence**: No two platforms share identical entity models. An author's affiliation in Crossref is an uncurated publisher-provided text string; in OpenAlex, it is mapped to a Research Organization Registry (ROR) canonical institution. In arXiv, abstracts are raw TeX/LaTeX strings; in OpenAlex, they are token-position inverted indices to circumvent copyright restrictions; in Semantic Scholar, they are plain extracted text.
* **Identifier Fragmentation**: Preprints lack DOIs upon creation; authors rarely supply ORCIDs consistently; venues undergo renaming and sponsor transitions.
* **Source Disagreements**: Publication years, author ordering, and citation counts systematically conflict across aggregators.

```
[arXiv: Preprint Observation] ─────────┐
[OpenAlex: Graph & Topic Observation] ─┼──► [Ingestion & Resolution] ──► [Canonical Scholarly Model]
[Crossref: Publisher DOI Registry] ────┤                                   (Decoupled, Normalized,
[Semantic Scholar: Citation Intents] ──┘                                    Audited, Idempotent)
```

### 1.2 The Mission of Canonical Scholarly Data Modeling
The goal of canonical scholarly data modeling is to construct an authoritative, query-optimized analytical relational layer (implemented via **DuckDB**) that satisfies five non-negotiable axioms:
1. **Separation of Observation from Identity**: An entity's canonical representation must exist independently of any vendor's proprietary ID.
2. **Lossless Provenance**: The system must track *who asserted what, when, and with what confidence*. Merging records must never erase raw observational history.
3. **Deterministic Conflict Resolution**: Source disagreements must be resolved via transparent, deterministic priority policies rather than ad-hoc overwrites.
4. **Strict Ingestion Idempotency**: Ingestion pipelines must be replayable and fault-tolerant; repeated runs over identical or overlapping data batches must yield identical, corruption-free state.
5. **Analytical Ergonomics**: The data platform must empower downstream research queries—such as citation velocity tracking, venue authority ranking, and co-authorship community detection—with sub-second relational SQL performance.

---

## 2. Scholarly Data Landscape

To design a robust ingestion and canonicalization platform, data engineers must understand the concrete API semantics, strengths, and failure modes of major scholarly providers.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               SCHOLARLY DATA PROVIDERS                                 │
├────────────────────┬────────────────────┬────────────────────┬─────────────────────────┤
│       arXiv        │      OpenAlex      │      Crossref      │    Semantic Scholar     │
├────────────────────┼────────────────────┼────────────────────┼─────────────────────────┤
│ * Velocity: Hours  │ * Velocity: Weekly │ * Velocity: Days   │ * Velocity: Weekly      │
│ * Preprints        │ * Global Open Graph│ * Publisher Record │ * Citation Intents      │
│ * Uncurated text   │ * ROR / Concepts   │ * DOI Authority    │ * Influential Citations │
│ * TeX abstracts    │ * Inverted Index   │ * JATS XML / Paywall│ * PaperId / CorpusId   │
└────────────────────┴────────────────────┴────────────────────┴─────────────────────────┘
```

### 2.1 arXiv (The Bleeding Edge Preprint Repository)
* **FACT**: Established in 1991, arXiv is the primary preprint repository for Physics, Mathematics, Computer Science, Quantitative Biology, and Machine Learning.
* **FACT**: Identifiers follow two conventions:
  - *Modern format* (post-2007): `YYMM.NNNNN` (e.g., `1706.03762`), with optional version suffix `vN` (e.g., `1706.03762v5`).
  - *Legacy format* (pre-2007): `arch-ive/YYMMNNN` (e.g., `hep-th/9901001`).
* **FACT**: arXiv exposes metadata via OAI-PMH (XML) and bulk JSON metadata dumps.
* **Semantics & Idiosyncrasies**:
  - Contains no native citation graph.
  - Author entries are raw strings with no institutional IDs and rare ORCIDs.
  - Abstract text frequently contains embedded LaTeX markup (e.g., `$\mathcal{O}(n \log n)$`, `\textbf{Transformer}`).
  - Publication date represents the submission timestamp of the specific version, not peer-reviewed publication.
* **Role in Pipeline**: Earliest temporal detector of technological breakthroughs and rising architectural paradigms.

### 2.2 OpenAlex (The Comprehensive Open Academic Graph)
* **FACT**: Successor to Microsoft Academic Graph (MAG), operated by OurResearch, cataloging >250M works.
* **FACT**: Exposes structured REST APIs and monthly AWS S3 / Databrick flat file dumps.
* **FACT**: Entity IDs are URI-formatted strings with specific type prefixes:
  - Work: `https://openalex.org/W...`
  - Author: `https://openalex.org/A...`
  - Source/Venue: `https://openalex.org/S...`
  - Institution: `https://openalex.org/I...`
  - Topic/Concept: `https://openalex.org/T...` or `C...`
* **Semantics & Idiosyncrasies**:
  - Abstracts are stored as an **inverted index** (`abstract_inverted_index`: `{"word": [pos1, pos2]}`) to comply with publisher licensing restrictions. A reconstruction algorithm is required to convert this back into human-readable text.
  - Disambiguates authors and institutions using proprietary machine learning models. Authors are linked to ROR IDs.
  - References are provided as lists of OpenAlex Work URIs (`referenced_works: ["https://openalex.org/W..."]`).
* **Role in Pipeline**: Global topology spine, institutional mapping, and automated topic classification.

### 2.3 Crossref (The Publisher DOI Registry)
* **FACT**: The official Digital Object Identifier (DOI) registration agency for scholarly publishing, covering commercial, society, and open-access publishers.
* **FACT**: Primary key is the normalized DOI (e.g., `10.1145/3292500.3330964`).
* **Semantics & Idiosyncrasies**:
  - The authoritative source of truth for **version of record (VoR)** metadata: official publication date, formal journal/conference title, volume, issue, page numbers, and publisher name.
  - Author affiliations are uncurated, heterogeneous text strings submitted directly by publishers (e.g., `"Dept of CS, Stanford Univ, CA"` vs `"Stanford University"`).
  - Reference lists are submitted as unstructured bibliographic text or partial lists of target DOIs. Many commercial publishers omit references unless participating in Initiative for Open Citations (I4OC).
* **Role in Pipeline**: Authority for peer-reviewed publication dates, formal venue names, and DOI minting validation.

### 2.4 Semantic Scholar (S2AG - Allen Institute for AI)
* **FACT**: Academic search engine and open graph indexing >200M papers, providing the Semantic Scholar Academic Graph (S2AG) API and datasets.
* **FACT**: Primary identifiers include `paperId` (40-character SHA1 hex hash) and `corpusId` (integer). External ID mappings include `DOI`, `ArXiv`, `PubMed`, `DBLP`, and `ACL`.
* **Semantics & Idiosyncrasies**:
  - Pioneers **Contextual Citation Modeling**: classifies citations by intent (`Methodology`, `Background`, `Result`) and flags `isInfluential` citations based on citation count, mention frequency in paper body, and excerpt sentiment.
  - Computes algorithmic metrics: `citationCount`, `referenceCount`, and `influentialCitationCount`.
* **Role in Pipeline**: High-signal noise filter, enabling technology trend miners to disregard superficial citations and focus on substantive methodological adoptions.

---

## 3. Canonical Data Modeling

### 3.1 Architectural Definition
```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         CANONICAL DATA MODEL (CDM)                               │
├──────────────────────────────────────────────────────────────────────────────────┤
│ A centralized, standardized domain representation that decouples disparate       │
│ upstream data producers from downstream analytical consumers.                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

* **FACT**: Coined in Enterprise Integration Patterns (Hohpe & Woolf), a Canonical Data Model eliminates the $O(N^2)$ point-to-point translation problem by routing all source schemas through an intermediate, authoritative $O(N)$ contract.
* **INFERENCE**: In scholarly data architectures, the Canonical Model is NOT merely an envelope containing raw JSON; it is a strictly typed, normalized relational schema that harmonizes heterogeneous entity models while preserving the underlying observational lineages.

### 3.2 Relational vs. Semi-Structured vs. Document Modeling
Data architects face trade-offs when selecting storage structures in DuckDB:

| Criterion | Fully Normalized Relational (3NF / Star) | Semi-Structured Document (Nested JSON) | Hybrid Relational + Typed Arrays (`LIST` / `STRUCT`) |
| :--- | :--- | :--- | :--- |
| **Storage Engine** | Columnar (DuckDB native vectors) | Text/Binary JSON blob | Columnar typed arrays |
| **Join Performance** | High (Vectorized hash joins) | Poor (Requires runtime JSON parsing) | High for parent; Requires unnest for child |
| **Constraint Enforcement** | Full (PK, UNIQUE, FK, CHECK) | None (Schema-on-read) | PK on parent; No FK/UNIQUE on nested items |
| **Schema Evolution** | Requires explicit migrations (`ALTER`) | Frictionless | Flexible at array level; migrations for structs |
| **Downstream SQL Ergonomics**| Standard SQL (`GROUP BY`, Window) | Verbose (`json_extract_string`, etc.) | High with list comprehensions / `UNNEST` |
| **Platform Tier** | **Gold (Canonical Layer)** | **Bronze (Raw Landing Layer)** | **Silver (Normalized Observation Layer)** |

### 3.3 The Scholarly Core Entities
A canonical scholarly platform models six fundamental domain concepts:
1. **Work**: An abstract creative intellectual contribution (e.g., an article, preprint, conference paper, review).
2. **Author**: An individual researcher contributing to creative intellectual output.
3. **Institution**: An organizational entity (university, research institute, corporation) with which authors are affiliated.
4. **Venue**: A publication platform (journal, conference proceedings, workshop, preprint repository).
5. **Authorship / Contribution**: The many-to-many junction binding an Author to a Work, qualified by sequence position and institutional affiliation at the time of publication.
6. **Citation**: A directed evidentiary edge linking a citing Work to a cited Work, annotated with context, intent, and timestamp.

---

## 4. Entity Identity

### 4.1 Concept: Identity vs. Identifier vs. State
```
┌───────────────────────────────────────────────────────────────────────────────────┐
│                       THE ENTITY IDENTITY ARCHITECTURE                            │
├───────────────────┬───────────────────────────────────────────────────────────────┤
│ Concept           │ Definition in Scholarly Data Engineering                      │
├───────────────────┼───────────────────────────────────────────────────────────────┤
│ Source ID         │ Local vendor identifier (e.g., OpenAlex `W123`, S2 `204e3...`) │
│ Source Identity Key│ Normalized typed key (e.g., `doi:10.1145/...`, `arxiv:1706.03762`)│
│ Candidate Cluster │ Set of source identity keys linked to the same intellectual work│
│ Canonical ID      │ Deterministic surrogate key representing the real-world entity│
│ Entity State      │ Mutable attribute values (title, citation count, venue)       │
└───────────────────┴───────────────────────────────────────────────────────────────┘
```

* **Why it matters**: Conflating a source-derived identity key with the canonical identity leads to split identity clusters. If one naive system mints `UUIDv5(namespace_doi, doi)` and another mints `UUIDv5(namespace_arxiv, arxiv_id)` independently, the exact same paper discovered from arXiv and then Crossref would generate two disconnected "canonical" UUIDs!
* **Correct Modeling Principle**:
  1. Distinguish **Source-Derived Identity Keys** from the **Resolved Canonical Identity**.
  2. The ingestion engine extracts all normalized keys from a source record (`doi:...`, `arxiv:...`, `s2:...`).
  3. The resolver searches the existing `canonical_work_identifiers` index.
  4. If any key matches an existing canonical entity, that existing `canonical_work_id` is retained.
  5. Only when NO existing match is found, the system mints a new `canonical_work_id` deterministically from the primary resolved anchor key (e.g. `UUIDv5(NAMESPACE_CANONICAL_WORK, primary_key)` where priority is `doi:` > `arxiv:` > internal cluster key).

---

## 5. Entity Resolution & Deduplication

### 5.1 Deduplication vs. Entity Resolution
* **FACT**: **Deduplication** is the elimination of exact duplicate records within a single source or dataset.
* **FACT**: **Entity Resolution (ER)** is the probabilistic or deterministic task of determining whether two distinct records—originating from different schemas, timestamps, or sources—refer to the same underlying real-world entity.

### 5.2 Deterministic Multi-Pass Resolution Strategy & Match Tiers
In scholarly data platforms, entity resolution must classify match confidence explicitly rather than blindly auto-merging:

```
┌───────────────────┬───────────────────────────┬───────────────────────────────────────┐
│ Match Tier        │ Evidence Rule             │ Resolution Action                     │
├───────────────────┼───────────────────────────┼───────────────────────────────────────┤
│ **EXACT_MATCH**   │ Normalized DOI match      │ Automatic canonical merge             │
│ **EXACT_MATCH**   │ Normalized arXiv ID match │ Automatic canonical merge             │
│ **PROBABLE_MATCH**│ Title + Year + Author fp  │ CANDIDATE ONLY: Log to review queue;  │
│                   │                           │ do NOT auto-merge to prevent collision│
│ **NO_MATCH**      │ No known keys match       │ Mint new canonical entity             │
└───────────────────┴───────────────────────────┴───────────────────────────────────────┘
```

* **Critical Rule on Fingerprints**: Composite fingerprints (`title_slug + publication_year + first_author`) must **NEVER** trigger automatic canonical merges in production pipelines. Variations between conference versions, journal extensions, corrigenda, preprints, and author homonyms produce severe false-positive collisions. Fingerprint matches are flagged as `CANDIDATE_ONLY`.

---

## 8. Citation Graph Modeling & Stub Lifecycle

### 8.1 Directed Graph Properties
* **FACT**: The scholarly citation graph is an open-world directed graph where citing papers reference works outside the local corpus.

### 8.2 Stub Entity Semantics & Upgrade Path
When paper $P$ cites an unindexed work identified only by DOI `10.1234/xyz`:
1. **Stub Creation**: The system provisions a stub work in `canonical_works`:
   - `canonical_work_id = UUIDv5(NAMESPACE_CANONICAL_WORK, "doi:10.1234/xyz")`
   - `is_stub = TRUE`
   - `stub_reason = 'DANGLING_CITATION_TARGET'`
   - `created_from_source = 'semantic_scholar'`
   - `title = '[Stub Citation Target: 10.1234/xyz]'`
2. **Referential Integrity**: The citation edge in `canonical_citations` references `citing_work_id` and `cited_work_id` without foreign key violation.
3. **Stub-to-Canonical Upgrade**:
   - When the actual source metadata for `10.1234/xyz` is subsequently ingested (e.g. from Crossref or OpenAlex):
   - The resolver locates the existing stub work via `canonical_work_identifiers`.
   - Instead of inserting a new work, it **upgrades** the stub in-place:
     `UPDATE canonical_works SET is_stub = FALSE, title = ?, abstract = ?, updated_at = ? WHERE canonical_work_id = ?`
   - All previously created inbound citation edges immediately point to the rich, fully resolved canonical work with zero broken foreign keys or duplicate entities!

---

## 9. Provenance & Lineage Architecture

### 9.1 The Four Tiers of Lineage & Provenance
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       LINEAGE & PROVENANCE ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Ingestion Run Lineage (`ingestion_runs`):                                │
│    run_id, source, input_uri, input_hash, record counts, versions, timestamps│
│ 2. Raw File & Payload Landing (`raw_source_manifest` / `raw_records`):     │
│    Immutable file on disk + SHA256 payload hash verification                │
│ 3. Record-Level Observation (`source_work_observations`):                   │
│    source, source_work_id, observed_at, normalized attributes, run_id       │
│ 4. Attribute-Level Provenance (`canonical_work_provenance`):                │
│    canonical_work_id, attribute_name, winning_source, source_observation_id │
└─────────────────────────────────────────────────────────────────────────────┘
```

* **Eliminating Duplicate Concepts**:
  - `source_work_observations` records the full entity observation snapshot from the source at that run.
  - `canonical_work_provenance` records the lineage pointer: which `source_observation_id` won for each canonical attribute (`title`, `abstract`, `venue`, `publication_date`).
  - `metrics_provenance` is specifically reserved for append-only time-series snapshots of volatile metrics (`citation_count`, `influential_citation_count`) captured over successive ingestion runs.

---

## 15. Data Quality Assertion Framework & Quarantine

Data pipelines must enforce explicit Data Quality (DQ) contracts with defined severity levels and recovery actions:

```
┌────────┬─────────────────────────────┬───────────┬───────────────────────────────────────────┐
│ Rule   │ Condition / Assertion       │ Severity  │ Action on Violation                       │
├────────┼─────────────────────────────┼───────────┼───────────────────────────────────────────┤
│ **DQ-01**│ Identifier format & checksum│ REJECT_ID │ Quarantines malformed ID; continues parse │
│        │ (Valid DOI / arXiv / ORCID) │           │ if alternative identifiers exist.         │
│ **DQ-02**│ Title completeness          │ QUARANTINE│ Rejects entire record to `quarantine`     │
│        │ (len >= 3, not placeholder) │           │ table; excludes from Gold resolution.     │
│ **DQ-03**│ Publication year boundaries │ SANITIZE  │ Sets `publication_year = NULL`; logs      │
│        │ (1665 <= year <= now + 1)   │           │ warning; allows canonical ingestion.      │
│ **DQ-04**│ Citation graph valid edge   │ DROP_EDGE │ Discards self-citations (`citing==cited`);│
│        │ (`citing_id != cited_id`)   │           │ prevents cyclic self-loops.               │
│ **DQ-05**│ Authorship validity         │ SANITIZE  │ Defaults position >= 1; preserves valid   │
│        │ (position >= 1, name != '') │           │ author mentions; drops blank names.       │
└────────┴─────────────────────────────┴───────────┴───────────────────────────────────────────┘
```

---

## 6. Identifier Strategy

### 6.1 Systematic Identifier Analysis
Scholarly systems interact with six primary identifier classes:

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                             SCHOLARLY IDENTIFIERS TAXONOMY                               │
├───────────────┬─────────────────────────┬──────────────────┬─────────────────────────────┤
│ Identifier    │ Real-World Target       │ Syntax Standard  │ Normalization Rule          │
├───────────────┼─────────────────────────┼──────────────────┼─────────────────────────────┤
│ **DOI**       │ Works, Datasets         │ ISO 26324        │ Lowercase, strip `https://` │
│ **arXiv ID**  │ Preprints               │ arXiv Spec       │ Lowercase, strip `vN`       │
│ **ORCID**     │ Authors                 │ ISO 7746         │ 16-char hyphenated, check-digit│
│ **ROR ID**    │ Institutions            │ ROR Schema v2    │ Lowercase URL or 9-char code│
│ **OpenAlex ID**│ Works/Authors/Venues    │ OpenAlex URI     │ Extract Prefix + AlphaNum   │
│ **S2 PaperId**│ S2 Works                │ 40-char SHA1 Hex │ Lowercase 40-char hex       │
└───────────────┴─────────────────────────┴──────────────────┴─────────────────────────────┘
```

### 6.2 Normalization Algorithms
* **DOI Normalization**:
  $$N(\text{DOI}) = \text{lower}\Big(\text{regex\_replace}\big(\text{raw}, \text{`\^(https?://(dx\.)?doi\.org/\|doi:)'}, \text{`'}\big)\Big)$$
  *Example*: `https://doi.org/10.1145/3292500.3330964` $\longrightarrow$ `10.1145/3292500.3330964`
* **arXiv ID Normalization**:
  $$N(\text{arXiv}) = \text{lower}\Big(\text{regex\_replace}\big(\text{regex\_replace}(\text{raw}, \text{`\^arxiv:'}, \text{`'}\big), \text{`v[0-9]+$'}, \text{`'}\big)\Big)$$
  *Example*: `arXiv:1706.03762v5` $\longrightarrow$ `1706.03762`
  *Critical distinction*: The unversioned ID represents the *canonical work*; the versioned ID represents the specific *source observation*.
* **ORCID Normalization**:
  $$N(\text{ORCID}) = \text{regex\_extract}\big(\text{raw}, \text{`[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]'}\big)$$
  *Validation*: Must satisfy ISO/IEC 7064 MOD 11-2 check-digit verification.

### 6.3 Relational Modeling of External Identifiers
* **Question A**: Should external IDs be stored as `STRUCT(source VARCHAR, id VARCHAR)[]` on the `works` table, or in a separate relational table `work_identifiers`?
* **Trade-off Analysis**:
  - `STRUCT[]` inside `works`:
    - *Advantage*: Compact for serialization; retrieves all IDs with a single row fetch.
    - *Disadvantage*: Severe indexing penalty in DuckDB. Searching for an entity by DOI requires an unnest or list lambda filter (`list_filter(...)`). DuckDB cannot enforce a `UNIQUE` constraint across array elements, permitting duplicate DOIs across different works.
  - Separate `work_identifiers` table:
    - *Advantage*: Allows compound primary key `(identifier_type, normalized_value) PRIMARY KEY`, enforcing that no two canonical works claim the same DOI. Enables instant vectorized B-Tree index lookups for ingestion deduplication.
* **DESIGN DECISION**:
  **Adopt a Hybrid Architecture.**
  1. Maintain a dedicated, indexed relational table `canonical_work_identifiers` for strict uniqueness, multi-pass entity resolution, and bi-directional lookups.
  2. Materialize high-cardinality lookup keys (`canonical_doi`, `canonical_arxiv_id`) as first-class, indexed columns directly on `canonical_works` for zero-join analytical ergonomics.

---

## 7. Relationship Modeling

### 7.1 The Authorship Many-to-Many Relationship
The relationship between Works and Authors is not a simplistic join; it possesses critical domain attributes:
* **Sequence / Position**: First author (lead investigator), last author (senior/corresponding author in biomedical disciplines), or alphabetical order (typical in pure mathematics/theoretical CS).
* **Corresponding Status**: Boolean flag indicating legal correspondence responsibility.
* **Affiliation at Publication**: An author may move from Stanford to Google DeepMind. Their historical affiliation on a 2017 work must remain Stanford, even if their current author profile lists Google DeepMind.

```
┌─────────────────┐       ┌───────────────────────────────┐       ┌──────────────────┐
│ canonical_works │───1:N─┤ canonical_work_authors        │─N:1───│ canonical_authors│
└─────────────────┘       ├───────────────────────────────┤       └──────────────────┘
                          │ * canonical_work_id (FK)      │
                          │ * canonical_author_id (FK)    │
                          │ * canonical_institution_id(FK)│
                          │ * author_position (INT)       │
                          │ * raw_author_name (VARCHAR)   │
                          │ * raw_affiliation_str (VARCHAR)
                          └───────────────────────────────┘
```

* **Failure Mode**: Normalizing the author directly to their current institution, destroying the historical affiliation evidence of the research publication.
* **Correct Modeling Principle**:
  `canonical_work_authors` captures the snapshot state of the author's name and affiliation *at the time of publication*, while foreign keys link to the canonical entities.

---

## 8. Citation Graph Modeling

### 8.1 Directed Graph Properties
* **FACT**: The scholarly citation graph is a directed acyclic graph (DAG) in theory (papers cite the past), but in practice contains cycles due to concurrent preprint citations, cross-citations in edited volumes, and publication delay anomalies.
* **FACT**: Graph density is highly skewed: power-law distribution where 1% of papers attract 90% of citations.

### 8.2 The Open-World Dangling Edge Problem
* **Concept**: When ingesting a newly published paper $P$, it cites 40 older papers $C_1, \dots, C_{40}$. The vast majority of these cited papers may not yet exist in our local DuckDB database.
* **Failure Mode**:
  Enforcing a strict relational foreign key constraint:
  ```sql
  CREATE TABLE citations (
      citing_work_id VARCHAR REFERENCES works(canonical_work_id),
      cited_work_id VARCHAR REFERENCES works(canonical_work_id)
  );
  ```
  *Consequence*: Ingesting paper $P$ will crash with a `ConstraintException: Violates foreign key constraint` because $C_1, \dots, C_{40}$ are missing.
* **Architectural Solutions**:
  1. **Option A: Unconstrained Graph Edge Table**: Omit the foreign key on `cited_work_id`. Store resolved canonical IDs if known, or normalized target identifiers (e.g., target DOI).
  2. **Option B: Automatic Stub Entity Provisioning**: When an unindexed cited paper is encountered, dynamically create a "stub" record in `canonical_works` with `is_stub = TRUE`, populating only its known identifier.
* **DESIGN DECISION**:
  Implement **Option B with Dual-Layer Edge Storage**:
  - `canonical_citations` maintains strict referential integrity by automatically inserting lightweight stub works (`is_stub = TRUE`) when a target work is unresolved.
  - `citation_context` captures citation intent (`Methodology`, `Background`, `Result`) and `is_influential` flags derived from Semantic Scholar.

---

## 9. Provenance

### 9.1 The Levels of Provenance
Data lineage in scientific data systems operates across three distinct granularities:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LEVELS OF PROVENANCE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Pipeline Run Provenance: Execution timestamp, git commit, runtime config │
│ 2. Record-Level Provenance: Source provider, payload hash, ingestion batch  │
│ 3. Attribute-Level Provenance: Which source provided the title, year, venue │
└─────────────────────────────────────────────────────────────────────────────┘
```

* **Why it matters**: If OpenAlex reports 150 citations and Semantic Scholar reports 95 citations, the data platform cannot arbitrarily pick one without recording the observation metadata. An empirical research paper citing these figures must be able to reproduce the exact state observed on that date.

### 9.2 Observation vs. Current State
* **Concept**:
  - **Source Observation**: An immutable, append-only record of what an external API returned at a specific timestamp.
  - **Current State**: The consolidated, synthesized view currently accepted as authoritative.
* **Failure Mode**:
  Overwriting the current state directly via `ON CONFLICT DO UPDATE` without saving the historical observation. If the upstream provider has a bug or introduces corrupt data, the original valid observation is permanently obliterated.
* **Correct Modeling Principle**:
  **Never mutate observations.** Observations land in an append-only Silver layer (`source_work_observations`). The Gold layer (`canonical_works`) is a deterministic projection derived from these observations via explicit resolution policies.

---

## 10. Source Conflicts & Disagreements

### 10.1 Typical Disagreement Scenarios
Scholarly aggregators frequently report contradictory metadata for identical papers:

| Attribute | Source A (e.g., arXiv) | Source B (e.g., Crossref) | Root Cause of Disagreement |
| :--- | :--- | :--- | :--- |
| **Publication Year** | `2021` (Preprint date) | `2023` (Journal print date) | Differing definitions of "publication" |
| **Title** | `"BERT: Pre-training of Deep..."` | `"BERT: PRE-TRAINING OF DEEP..."` | Publisher typesetting style |
| **Author Count** | 5 authors | 3 authors + "et al." | Truncation in secondary indexing |
| **Venue Name** | `"arXiv.org"` | `"NAACL-HLT 2019"` | Venue escalation post peer-review |

### 10.2 Conflict Resolution Hierarchy
To resolve attribute conflicts deterministically without human intervention, the canonicalization engine implements a **Source Authority Priority Matrix**:

```
Attribute: Publication Date & Venue
Crossref (Publisher VoR) > OpenAlex (Curated) > S2AG > arXiv (Preprint fallback)

Attribute: Citation Velocity & Intents
Semantic Scholar (S2AG) > OpenAlex > Crossref (Static references only)

Attribute: Abstract & Topics
Semantic Scholar (Clean text) > arXiv (Complete TeX) > OpenAlex (Reconstructed Inverted Index)

Attribute: Institutional Hierarchy
OpenAlex (ROR-aligned) > Crossref (Raw strings) > arXiv (None)
```

---

## 11. Medallion Architecture: Raw → Normalized → Canonical

To guarantee auditability, recovery, and analytical velocity, data pipelines follow a three-tier Medallion architecture:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            MEDALLION LAYERS                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   BRONZE (Raw Landing)                                                       │
│   * Append-only JSON / JSONL payloads                                        │
│   * Raw HTTP responses, fetch timestamps, payload MD5/SHA256 hashes          │
│   * Schema: Flexible, unindexed, zero data transformation                    │
│                                                                              │
│                                      ▼                                       │
│   SILVER (Normalized Observations)                                           │
│   * Typed relational tables per source: `source_arxiv_works`, `source_oa_...`│
│   * Identifiers normalized; syntax standardized; dates validated             │
│   * Preserves exact source assertions; 1 row per source observation          │
│                                                                              │
│                                      ▼                                       │
│   GOLD (Canonical Domain Model)                                              │
│   * Consolidated entities: `canonical_works`, `canonical_authors`           │
│   * Multi-pass entity resolution; authoritative conflict policies applied    │
│   * Strict relational constraints; sub-second analytical indexing            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. Incremental Ingestion & CDC

### 12.1 Incremental Strategies
Scientific corpora grow by millions of records annually. Full table re-scans are computationally prohibitive.
* **Watermark Tracking**: Maintain an `ingestion_watermarks` table recording `(source_name, entity_type, last_cursor_or_timestamp)`.
* **Change Data Capture (CDC)**: Ingest only records with `updated_date >= last_watermark`.
* **Late-Arriving Citations**: A citation edge created in 2024 can point to a paper written in 1980. The ingestion engine must handle backfilled edges without requiring a re-index of the 1980 paper's metadata.

---

## 13. Idempotency

### 13.1 Mathematical Idempotency
An ingestion operation $f$ is idempotent if applying it multiple times to the same input state $x$ yields the identical output state:
$$f(f(x)) = f(x)$$

### 13.2 Concrete Scholarly Failure Mode
* An ingestion worker crashes halfway through parsing a 50,000-line JSONL file from arXiv.
* A naive pipeline without idempotency simply restarts the batch.
* *Result*: Counters are incremented twice; citation edges are duplicated; author-work associations are multiplied.
* **Implementation Requirement**:
  1. Every raw batch is identified by a deterministic `batch_id` computed from the hash of the file contents.
  2. Staging tables use atomic transactions:
     `BEGIN TRANSACTION; DELETE FROM staging WHERE batch_id = ?; INSERT ...; COMMIT;`
  3. Canonical merges use deterministic keys: identical inputs produce identical surrogate keys and upsert matching records without row multiplication.

---

## 14. Schema Evolution

* **FACT**: Scholarly APIs frequently introduce new fields (e.g., OpenAlex added Sustainable Development Goals `sdgs` and primary topics).
* **Defensive Schema Design**:
  - In the **Bronze layer**, store payloads as native DuckDB `JSON` columns. This guarantees that new upstream fields never break ingestion.
  - In the **Silver layer**, extract newly required attributes via explicit migration scripts (`ALTER TABLE ADD COLUMN`).
  - In the **Gold layer**, expose stable views or versioned schemas, shielding downstream trend-mining algorithms from raw upstream breaking changes.

---

## 15. Data Quality & Assertion Gates

Data pipelines must enforce strict validation gates before promoting records from Silver to Gold:
1. **Temporal Sanity**: Publication year must satisfy:
   $$1665 \le \text{publication\_year} \le \text{CurrentYear} + 1$$
   (1665 marks the founding of the *Philosophical Transactions of the Royal Society*).
2. **Text Non-Emptiness**: Title must contain at least 3 non-whitespace characters and not consist solely of placeholder strings (e.g., `"[Untitled]"`, `"None"`).
3. **Identifier Syntax Validity**: DOIs must match `^10\.\d{4,9}/[-._;()/:A-Za-z0-9]+$`.
4. **Referential Integrity**: An authorship entry cannot reference a non-existent author or work.

---

## 16. DuckDB as an Analytical Engine for Scholarly Data

### 16.1 Architectural Capabilities
* **FACT**: DuckDB is an in-process, columnar relational database management system (RDBMS) optimized for Online Analytical Processing (OLAP).
* **FACT**: Key engine properties verified in DuckDB 1.5.5:
  - Vectorized Execution Engine (SIMD-accelerated morsel-driven parallelism).
  - Native support for ACID transactions within single-file databases.
  - Native `JSON`, `STRUCT`, `LIST`, and `MAP` types with zero-copy column slicing.
  - Full SQL support for `MERGE INTO`, `INSERT ... ON CONFLICT DO UPDATE`, and window functions.
  - Zero-copy interop with Apache Arrow, Parquet, and Python memory spaces.

### 16.2 Limitations and Mitigations
* **Single-Writer Concurrency**: DuckDB allows multiple concurrent readers, but only a **single active writer** transaction per database file.
  - *Mitigation*: Ingestion workers should write partitioned Parquet files or staging tables independently, and execute batch merges into the canonical DuckDB file through a serialized writer process.
* **Memory Headroom**: Massive multi-million row joins can trigger out-of-core spilling.
  - *Mitigation*: Configure explicit memory limits (`SET max_memory = '8GB'`) and enable temporary directory spill storage.

---

## 17. DuckDB Nested Data: JSON vs. STRUCT vs. LIST

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DUCKDB NESTED TYPES FOR SCHOLARLY DATA                   │
├───────────────┬─────────────────────────────────────────────────────────────┤
│ Type          │ Best Scholarly Application                                  │
├───────────────┼─────────────────────────────────────────────────────────────┤
│ `JSON`        │ Bronze raw API payloads; unstructured publisher metadata    │
│ `VARCHAR[]`   │ Keywords, research topics, concept tags                     │
│ `STRUCT`      │ Point-in-time metrics snapshot (citations, velocity, rank)  │
│ `STRUCT[]`    │ Intermediate unnesting pipelines before 3NF table loading   │
└───────────────┴─────────────────────────────────────────────────────────────┘
```

* **Best Practice**: Use `read_json_auto()` to ingest heterogeneous JSONL files into staging tables, but project nested fields into normalized relational tables for downstream analytics to maximize vectorized columnar scan speeds.

---

## 18. Analytical Query Design

A canonical scholarly database is built to power complex analytical queries. The schema must be optimized for three canonical query patterns:
1. **Citation Velocity & Acceleration**:
   $$\text{Velocity}(W, t) = \frac{\Delta \text{Citations}(W)}{\Delta t}$$
   Requires fast index scans on `canonical_citations (cited_work_id, citing_year)`.
2. **Co-Authorship Network Traversal**:
   Extracting the collaboration graph requires joining `canonical_work_authors` on itself:
   $$W \bowtie A_1 \bowtie A_2 \quad (A_1 \ne A_2)$$
3. **Temporal Venue Impact Tracking**:
   Computing the rolling 2-year impact factor of top-tier AI venues requires grouping millions of citation edges filtered by publication year and venue tier.

---

## 19. Failure Modes in Scholarly Engineering

| Failure Mode | Root Cause | Impact | Correct Engineering Prevention |
| :--- | :--- | :--- | :--- |
| **DOI Case Duplication** | Case-sensitive string matching (`10.1145/...` vs `10.1145/...`) | Fractured identity, duplicate records | Strict lowercase normalization on entry |
| **Dangling Citations** | Cited paper not yet indexed | Relational FK violation aborts batch | Automatic stub entity creation |
| **Lost Metadata Overwrites** | Blind `ON CONFLICT DO UPDATE` from lower-tier source | High-quality metadata replaced with sparse data | Source Authority Priority Matrix |
| **Memory Exhaustion** | Ingesting 100GB JSON directly with `read_json` into memory | Pipeline OOM crash | Streaming JSONL chunking via DuckDB cursor |
| **Author Homonym Collisions** | Merging authors solely on `display_name` | "Wei Wang" merged into a single superhuman author | Scope authors to institutions / ORCID or leave unmerged |

---

## 20. Architectural Trade-offs

1. **Storage Footprint vs. Query Speed**:
   - Materializing external IDs both in `canonical_work_identifiers` and as summary columns on `canonical_works` increases storage by ~15%, but accelerates 95% of user lookup queries by avoiding an expensive relational join.
2. **Immediate Consistency vs. Ingestion Throughput**:
   - Running full multi-pass entity resolution synchronously on every ingested row throttles throughput.
   - *Resolution*: Perform deterministic single-key matching (DOI / arXiv) synchronously during ingestion; defer fuzzy multi-signal graph clustering to an asynchronous batch enrichment pass.

---

## 21. Lessons Learned from Production Scientific Databases

1. **Never trust upstream publication dates**: arXiv dates reflect preprint submissions; Crossref dates reflect publisher license minting; Semantic Scholar dates reflect web crawling. Explicitly record the date type (`preprint_date`, `published_date`).
2. **Abstracts require defensive cleaning**: Publishers insert copyright notices (`"Copyright (c) 2023 IEEE..."`), arXiv inserts TeX control codes, and OpenAlex requires inverted index reconstruction. Ingestion must include specialized text sanitation filters.
3. **Identifiers can be reassigned or deleted**: DOIs can be retracted or reassigned by publishers. Never assume natural keys are 100% immutable. Maintain internal surrogate canonical IDs.

---

## 22. Core Design Principles

```
1. Research before architecture.
2. Architecture before implementation.
3. Evidence before assumption.
4. Canonical identity ≠ source identity.
5. Current state ≠ source observation.
6. Deduplication ≠ entity resolution.
7. Ingestion ≠ canonicalization.
8. Provenance is data, not comments.
9. Idempotency is a requirement, not an optimization.
10. Tests are evidence, not decoration.
```
