# Snapshot provenance

The 1-month ingestion window slides daily and ingestion is additive (content-stable chunk
ids), so later runs saw slightly larger snapshots — always supersets that preserve every
question's provenance document. This table maps every number reported in the paper to the
corpus snapshot it was measured on. Arms compared within one table share a snapshot unless
noted.

| Result (paper table/section) | Corpus table | Chunks | Snapshot date | Runs |
|---|---|---|---|---|
| Pilot (Table: corpus scaling, 1mo column) | `ai_test` (July window) | 939 | 2026-07-16 | 1 |
| Main three-axis results (Table: main) | `ai_test` | 1,504 | 2026-08-08 | 3 |
| GraphRAG ablation chain (fusion, GPT-4o rebuild, V+G RRF) | `ai_test` | 1,504–1,737 | 2026-08-08..12 | 3 each |
| Explicit-link graph arm | `ai_test` | 1,737 | 2026-08-12 | 3 |
| LightRAG + vector re-pair (matched snapshot) | `ai_test` | 1,786 | 2026-08-16 | 3 passes (bit-identical) |
| Dense/sparse/fused leg decomposition (matched snapshot) | `ai_test` | 2,066 | 2026-08-18 | 3 each (bit-identical) |
| 6-month scaling cell | `ai_test_6mo` | 9,377 | 2026-08-08 | 1 |
| 12-month scaling cell | `ai_test_12mo` | 12,556 | 2026-08-08 | 1 |
| 5-year index (vector/agentic/rewrite/explicit-link) | `ai_test_5y` | 67,131 | 2026-08-12 | 3 |
| 5-year GraphRAG + hybrid (complete community layer) | `ai_test_5y` | 67,131 | 2026-08-12 (graph built 08-13..19) | 3 |
| Staleness set (N=50) | `ai_test_5y` / `ai_test` | 67,131 / 1,786 | 2026-08-16 | 3 |
| Kafka replication (1mo / 5y) | `kafka_test` / `kafka_test_5y` | 1,122 / 8,169 | 2026-08-17 | 3 |

Notes
- The 5-year graph: 233k entities, 754k relationships; community layer = 27,595 Leiden
  clusters (`random_seed=42`), all summarized and embedded (gpt-4o-mini).
- The ~6% internal-documentation chunks are excluded from the released question sets and
  cannot be released; public sources re-fetch deterministically from the snapshot dates.
