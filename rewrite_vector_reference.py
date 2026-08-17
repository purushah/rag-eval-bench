"""Rewrite-then-one-shot control: one LLM query rewrite, then a single vector retrieval.

Separates the agentic loop's two mechanisms: query REFORMULATION (kept) vs ITERATION
(removed). If this arm matches Agentic RAG, the loop's value is the rewrite; if it
matches one-shot Vector RAG, the value is iteration.
"""
from __future__ import annotations

from ..cost import CostMeter
from .base import Approach, BuildResult, QueryResult
from .vector_rag import VectorRAG


class RewriteVector(Approach):
    key = "rewrite-vector"
    name = "Rewrite-then-one-shot vector"

    def __init__(self, cfg, llm):
        super().__init__(cfg, llm)
        self._vector = VectorRAG(cfg, llm)

    def build(self) -> BuildResult:
        return BuildResult(meter=CostMeter(label="build:rewrite-vector"),
                           notes="reuses the shared embedding build")

    def answer(self, question: str) -> QueryResult:
        meter = CostMeter(label="search:rewrite-vector")
        msg = self.llm.chat(
            [{"role": "system", "content":
              "Rewrite the user's question as a single dense search query for a technical "
              "corpus (commits, issues, mailing list). Keep every identifier verbatim. "
              "Return ONLY the query."},
             {"role": "user", "content": question}], meter)
        rewritten = (msg.content or question).strip() or question
        context = self._vector._retrieve(rewritten, meter)
        ans = self._generate_answer(question, context, meter)
        return QueryResult(answer=ans, ranked_context=context, meter=meter,
                           trace=[f"rewrite: {rewritten[:120]}"])
