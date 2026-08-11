"""Explicit-link graph control — deterministic structure over raw chunks.

The GraphRAG negative result conflates two hypotheses: (a) graph structure does not
help this workload, vs. (b) LLM-based extraction destroys the evidence (identifiers,
release strings, authors) that raw chunks carry. This arm separates them: it uses the
corpus's NATIVE deterministic links (a FLINK-#### key appearing in a Jira chunk, its
PRs, and its commits IS the issue->PR->commit edge set) with no LLM extraction and no
graph store, and it returns ORIGINAL chunks.

Retrieval: (1) seed with identifiers named in the query (exact match), else vector
top-4; (2) expand one hop by fetching chunks that share the seeds' FLINK/FLIP keys
(the explicit link); (3) return up to top_k raw chunks, seeds first --- the same
context budget as Vector RAG. Build cost: the shared embedding build only.
"""
from __future__ import annotations

import re

from ..cost import CostMeter
from .base import Approach, BuildResult, QueryResult
from .vector_rag import VectorRAG

IDENT = re.compile(r"(FLINK-\d{4,6}|FLIP-\d{1,4}|#\d{4,6})")


class OracleGraphRAG(Approach):
    key = "oracle-graph"
    name = "Explicit-link graph (deterministic links, raw chunks)"

    def __init__(self, cfg, llm):
        super().__init__(cfg, llm)
        self._vector = VectorRAG(cfg, llm)

    def build(self) -> BuildResult:
        return BuildResult(
            meter=CostMeter(label="build:oracle-graph"),
            notes="reuses the shared embedding build; links are native identifiers (no extraction)",
        )

    def _fetch_by_keys(self, cur, keys: list[str], exclude_ids: set, limit: int) -> list[tuple[str, str]]:
        if not keys:
            return []
        pats = [f"%{k}%" for k in keys[:6]]
        cur.execute(
            f"SELECT id, text FROM {self.cfg.corpus_table} WHERE "
            + " OR ".join(["text ILIKE %s"] * len(pats))
            + " ORDER BY id LIMIT 40",
            pats,
        )
        return [(r[0], r[1] or "") for r in cur.fetchall() if r[0] not in exclude_ids][:limit]

    def answer(self, question: str) -> QueryResult:
        import psycopg

        meter = CostMeter(label="search:oracle-graph")
        k = self.cfg.top_k
        with psycopg.connect(self.cfg.pg_dsn) as conn, conn.cursor() as cur:
            q_keys = list(dict.fromkeys(IDENT.findall(question)))
            seeds: list[tuple[str, str]] = []
            if q_keys:
                seeds = self._fetch_by_keys(cur, q_keys, set(), k)
            if not seeds:
                # no identifier entry point: vector seed (metered), then link-expand
                vec = self._vector._retrieve(question, meter)[:4]
                cur.execute(
                    f"SELECT id, text FROM {self.cfg.corpus_table} WHERE text = ANY(%s)",
                    (vec,),
                )
                seeds = [(r[0], r[1] or "") for r in cur.fetchall()][:4]
                if not seeds:  # fallback if text lookup misses
                    seeds = [(f"vec-{i}", t) for i, t in enumerate(vec)]
            # one-hop expansion via shared keys (the explicit issue<->PR<->commit link)
            hop_keys = list(dict.fromkeys(
                key for _, txt in seeds for key in IDENT.findall(txt) if key not in q_keys
            ))
            seen = {cid for cid, _ in seeds}
            linked = self._fetch_by_keys(cur, (q_keys + hop_keys), seen, k - min(len(seeds), k))
        context = [t for _, t in seeds[:k]] + [t for _, t in linked]
        context = context[:k]
        ans = self._generate_answer(question, context, meter)
        return QueryResult(answer=ans, ranked_context=context, meter=meter)
