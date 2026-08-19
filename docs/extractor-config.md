# Ingestion and GraphRAG extractor configuration

## Chunking (all index arms share this)

- Splitter: whitespace-preserving character splitter
- `chunk_size = 1200` characters (`RAGBENCH_CHUNK_SIZE`)
- `chunk_overlap = 150` characters (`RAGBENCH_CHUNK_OVERLAP`)
- Chunk ids are content-stable (hash of source id + offset), making re-ingestion idempotent.

## Embeddings

- `text-embedding-3-large` (3,072 dims), pgvector exact scan (no ANN index at any tested scale).

## GraphRAG extraction (LlamaIndex `PropertyGraphIndex` over Neo4j + APOC)

- Extractor: `SchemaLLMPathExtractor`, model `gpt-4o-mini`, `num_workers=12`, `strict=False`
  (off-schema triples are kept).
- Entity ontology:
  `JIRA_ISSUE, PULL_REQUEST, COMMIT, EMAIL_THREAD, EXCEPTION, CONFIG_KEY, COMPONENT, VERSION, PERSON, API, DOCUMENT`
- Relation types:
  `FIXES, CAUSED_BY, CONFIGURES, DEPENDS_ON, PART_OF, MENTIONS, AUTHORED, REVIEWED_BY, MERGED_IN, REFERENCES, DISCUSSES`
- The validation schema is permissive but typed (e.g. `PULL_REQUEST -> FIXES|REFERENCES|MERGED_IN|MENTIONS`);
  the schema explicitly includes the entity and relation types needed by the multi-hop
  questions, so extraction misses are not schema impossibilities.
- Communities: Leiden (`graspologic hierarchical_leiden`, `max_cluster_size` default,
  `random_seed=42`); one gpt-4o-mini summary + one embedding per community; summary prompt
  inputs are capped (300 members / 1,500 edge lines / 90k chars) to fit model context.

## Retrieval

- Vector/hybrid: dense (pgvector cosine) + sparse (PostgreSQL FTS `plainto_tsquery`,
  `ts_rank`) fused by RRF with `k_rrf=60`, top-8 chunks. Note: measured on the benchmark, the
  sparse leg returns zero candidates for 151/163 questions (AND-semantics over
  sentence-length questions) — the hybrid is effectively dense; see the paper's
  decomposition.
- GraphRAG query path: local search (entity-seeded traversal) unioned with global search
  (community-summary vector match), returned as extracted-fact strings; `+ chunk fusion`
  maps facts back to provenance chunks and appends original text.
