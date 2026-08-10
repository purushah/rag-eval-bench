# Index It or Ask It? — Evaluation Sets

Question sets from **"Index It or Ask It? A Cost–Quality Benchmark of RAG, GraphRAG, Agentic
RAG, and Skill-Based Agentic Retrieval over Evolving Engineering Knowledge"** (under
submission, IEEE BigData 2026). The benchmark compares five retrieval strategies — vector RAG,
property-graph GraphRAG, agentic RAG, a live skill-based agent, and a closed-book baseline —
on **build cost, search cost, and quality** over Apache Flink developer knowledge (commits,
Jira, the dev@ mailing list, and documentation).

## Question sets

| File | N | What it tests |
|---|---|---|
| `eval/questions-pilot-v1.json` | 28 | Hand-written pilot set (general/Jira/PR/mailing-list strata; 13 reference seeded historical artifacts) |
| `eval/questions-main-v2.json` | 143 | Main set: corpus-mined, code-validated gold facts, identifier-gated, coverage-bucketed (recent / year / historical) |
| `eval/questions-main-v2-paraphrased.json` | 143 | The same questions reworded by a different provider's model (Claude), identifiers preserved verbatim — for miner/generator-coupling checks |
| `eval/questions-multihop.json` | 20 | Cross-document multi-hop: an issue's fix release **and** its resolving PR/commit author; each fact verified to appear in only one of the two linked documents |
| `eval/questions-staleness.json` | 50 | Staleness-stratified: questions whose correct answer **changed** over Flink's history (renamed config keys, deprecated APIs, removals); both the superseded and current forms verified present in a 5-year corpus |

Note: 20 additional main-set questions derive from internal (non-public) operator
documentation and are withheld; the paper reports headline results with and without them.

## Schema

Gold-fact questions (`pilot-v1`, `main-v2`, `multihop`):

```json
{
  "id": "v2-jira-3",
  "question": "…",
  "mustContain": ["FLINK-28576", "verbatim gold fact"],
  "source": "jira | pr-commit | commit | mailing-list | general | multi-hop",
  "bucket": "recent | year | historical",
  "provenance": "chunk id of the source document"
}
```

Metrics: **evidence recall** = fraction of `mustContain` facts present verbatim in the
retrieved context; **supported** = all facts present; **MRR** = reciprocal rank of the first
hit; answers are additionally scored 1–5 by an LLM judge distinct from the generator.

Staleness questions:

```json
{
  "id": "stale-4",
  "question": "Which connector class do I use to consume a Kafka topic…?",
  "currentPatterns": ["KafkaSource"],
  "stalePatterns": ["FlinkKafkaConsumer"],
  "current": "KafkaSource",
  "stale": "FlinkKafkaConsumer",
  "changed": "1.14 (FLIP-27 rework): FlinkKafkaConsumer deprecated…"
}
```

Answers are classified by a judge as recommending the **current** approach, the **stale** one
(without flagging deprecation), **both**, or **abstaining**, with the regex patterns as a
deterministic cross-check (mind the lookarounds — several pairs are substrings of each other,
e.g. `state.backend` ⊂ `state.backend.type`). `staleness_eval_reference.py` is the reference
scorer (it imports the benchmark harness; harness release to follow).

## Reproducibility notes

- Corpus: public Apache Flink sources (GitHub `apache/flink`, ASF Jira, `dev@` archives),
  re-fetchable from the snapshot dates in the paper (pilot 2026-07-16, main 2026-08-08).
- Mined gold facts are verbatim substrings of their provenance documents, validated in code,
  and each question carries at least one discriminating identifier (`FLINK-####`, `FLIP-##`,
  dotted config keys, PR numbers, author handles).
- Multi-hop facts are cross-document by construction: the release fact appears only in the
  Jira document and the author fact only in the PR/commit document.

## Citation

```bibtex
@inproceedings{shah2026indexitoraskit,
  title     = {Index It or Ask It? A Cost--Quality Benchmark of RAG, GraphRAG, Agentic RAG,
               and Skill-Based Agentic Retrieval over Evolving Engineering Knowledge},
  author    = {Shah, Purshotam and Unhale, Shubhankar and Zwick-Schachter, Isaiah and
               Gresch, Aaron and Williamson, Chris},
  booktitle = {IEEE International Conference on Big Data (BigData)},
  year      = {2026},
  note      = {Under submission}
}
```

## License

Apache License 2.0 (see `LICENSE`). Question text and gold facts derive from public Apache
Flink project artifacts (ASF, Apache-2.0).
