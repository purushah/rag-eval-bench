#!/usr/bin/env python3
"""Second GraphRAG arm: LightRAG (lightrag-hku) over the ai_test corpus.

Builds a LightRAG index from all chunks in Postgres table ai_test, then
answers the main (questions-v2.json) and multi-hop (questions-multihop.json)
question sets with mode="hybrid", scoring evidence recall against the
retrieved context (QueryParam(only_need_context=True)).

Retrieval is deterministic given the built index, so the question sets are
run ONCE (no 3x repetition as in the LLM-judge arms).

Run with the dedicated venv (NOT the repo .venv):
  <scratchpad>/lightrag-venv/bin/python scripts/lightrag_arm.py [--skip-build]

Results: results/lightrag_results.json
"""

import argparse
import asyncio
import json
import os
import sys
import time
from functools import partial
from pathlib import Path

# ---------------------------------------------------------------- config
REPO = Path(__file__).resolve().parent.parent
SCRATCH = Path(
    "/private/tmp/claude-501/-Users-purushah-views-flink-ai-service-flink-ai-service/"
    "e4e718f6-59c3-42e5-991a-d68d59df9414/scratchpad"
)
WORKDIR = SCRATCH / "lightrag_workdir"
DSN = "postgresql://purushah@localhost:5432/flink_ai"
KEY_FILE = Path("/private/tmp/open_ai_key.txt")
QUESTIONS_MAIN = REPO / "eval" / "questions-v2.json"
QUESTIONS_MULTIHOP = REPO / "eval" / "questions-multihop.json"
RESULTS_FILE = REPO / "results" / "lightrag_results.json"
INSERT_BATCH = 50
LLM_MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 3072
QUERY_MODE = "hybrid"  # falls back to "mix" then "local" if unavailable

os.environ["OPENAI_API_KEY"] = KEY_FILE.read_text().strip()

from lightrag import LightRAG, QueryParam  # noqa: E402
from lightrag.llm.openai import gpt_4o_mini_complete, openai_embed  # noqa: E402
from lightrag.utils import EmbeddingFunc  # noqa: E402
from lightrag.kg.shared_storage import initialize_pipeline_status  # noqa: E402


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_chunks() -> list[tuple[str, str]]:
    import psycopg

    with psycopg.connect(DSN) as conn:
        rows = conn.execute("SELECT id, text FROM ai_test ORDER BY id").fetchall()
    return [(r[0], r[1]) for r in rows if r[1] and r[1].strip()]


async def make_rag() -> LightRAG:
    embed = EmbeddingFunc(
        embedding_dim=EMBED_DIM,
        max_token_size=8191,
        model_name=EMBED_MODEL,
        send_dimensions=True,
        func=partial(openai_embed.func, model=EMBED_MODEL, embedding_dim=EMBED_DIM),
    )
    rag = LightRAG(
        working_dir=str(WORKDIR),
        llm_model_func=gpt_4o_mini_complete,
        llm_model_name=LLM_MODEL,
        embedding_func=embed,
        llm_model_max_async=12,
        embedding_func_max_async=16,
        max_parallel_insert=8,
        enable_llm_cache=True,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    return rag


async def build(rag: LightRAG, chunks: list[tuple[str, str]]) -> float:
    log(f"building LightRAG index over {len(chunks)} chunks ...")
    t0 = time.time()
    for i in range(0, len(chunks), INSERT_BATCH):
        batch = chunks[i : i + INSERT_BATCH]
        ids = [c[0] for c in batch]
        texts = [c[1] for c in batch]
        await rag.ainsert(texts, ids=ids, file_paths=ids)
        log(f"  inserted {min(i + INSERT_BATCH, len(chunks))}/{len(chunks)}"
            f" ({time.time() - t0:.0f}s elapsed)")
    secs = time.time() - t0
    log(f"build done in {secs:.0f}s")
    return secs


def load_questions(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data["questions"] if isinstance(data, dict) else data


async def query_set(rag: LightRAG, questions: list[dict], label: str,
                    mode: str) -> tuple[dict, bool]:
    """Returns (result-dict, context_available)."""
    per_q = []
    ctx_available = True
    for i, q in enumerate(questions, 1):
        qid = q.get("id", f"{label}-{i}")
        qtext = q["question"]
        facts = q["mustContain"]
        context, answer = "", ""
        try:
            context = await rag.aquery(
                qtext, param=QueryParam(mode=mode, only_need_context=True,
                                        enable_rerank=False))
            if not isinstance(context, str):
                context = json.dumps(context, default=str)
        except Exception as e:  # noqa: BLE001
            log(f"  [{label} {qid}] context query failed: {e}")
            ctx_available = False
        try:
            answer = await rag.aquery(
                qtext, param=QueryParam(mode=mode, enable_rerank=False))
            if not isinstance(answer, str):
                answer = str(answer)
        except Exception as e:  # noqa: BLE001
            log(f"  [{label} {qid}] answer query failed: {e}")
        haystack = context if context else answer
        scored_on = "context" if context else "answer"
        hay_lower = haystack.lower()
        hits = [f for f in facts if f.lower() in hay_lower]
        recall = len(hits) / len(facts) if facts else 0.0
        per_q.append({
            "id": qid,
            "recall": round(recall, 4),
            "supported": len(hits) == len(facts),
            "missing": [f for f in facts if f not in hits],
            "scored_on": scored_on,
            "answer": answer,
        })
        if i % 10 == 0 or i == len(questions):
            log(f"  [{label}] {i}/{len(questions)} queried")
    n = len(per_q)
    mean_recall = sum(p["recall"] for p in per_q) / n if n else 0.0
    supported_pct = 100.0 * sum(p["supported"] for p in per_q) / n if n else 0.0
    return ({
        "n": n,
        "mean_recall": round(mean_recall, 4),
        "supported_pct": round(supported_pct, 2),
        "per_question": per_q,
    }, ctx_available)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-build", action="store_true",
                    help="reuse existing index in working dir")
    ap.add_argument("--mode", default=QUERY_MODE)
    args = ap.parse_args()

    WORKDIR.mkdir(parents=True, exist_ok=True)
    rag = await make_rag()

    build_seconds = None
    build_notes = f"lightrag-hku 1.5.6, llm={LLM_MODEL}, embed={EMBED_MODEL} ({EMBED_DIM}d), " \
                  f"batch={INSERT_BATCH}, llm_max_async=12, max_parallel_insert=8"
    if args.skip_build:
        build_notes += "; build skipped (reused existing workdir)"
        log("skipping build, reusing existing index")
    else:
        chunks = load_chunks()
        build_seconds = await build(rag, chunks)
        build_notes += f"; {len(chunks)} source chunks inserted"

    # pick query mode with fallback
    mode = args.mode
    probe_q = "What is Apache Flink?"
    for candidate in [mode, "mix", "local"]:
        try:
            await rag.aquery(probe_q, param=QueryParam(
                mode=candidate, only_need_context=True, enable_rerank=False))
            mode = candidate
            break
        except Exception as e:  # noqa: BLE001
            log(f"mode {candidate!r} probe failed: {e}")
    log(f"using query mode: {mode}")

    main_qs = load_questions(QUESTIONS_MAIN)
    mh_qs = load_questions(QUESTIONS_MULTIHOP)
    log(f"querying main set ({len(main_qs)} questions), single pass "
        "(retrieval deterministic; not repeated 3x)")
    main_res, ctx1 = await query_set(rag, main_qs, "main", mode)
    log(f"querying multihop set ({len(mh_qs)} questions)")
    mh_res, ctx2 = await query_set(rag, mh_qs, "multihop", mode)

    out = {
        "arm": "lightrag",
        "mode": mode,
        "build_seconds": round(build_seconds, 1) if build_seconds else None,
        "build_notes": build_notes,
        "context_available": ctx1 and ctx2,
        "scoring": "evidence recall = fraction of mustContain facts present "
                   "(case-insensitive substring) in retrieved context; "
                   "single pass, no repetition",
        "main": main_res,
        "multihop": mh_res,
    }
    RESULTS_FILE.parent.mkdir(exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(out, indent=2))
    log(f"wrote {RESULTS_FILE}")
    log(f"MAIN: mean_recall={main_res['mean_recall']} "
        f"supported_pct={main_res['supported_pct']}")
    log(f"MULTIHOP: mean_recall={mh_res['mean_recall']} "
        f"supported_pct={mh_res['supported_pct']}")
    await rag.finalize_storages()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
