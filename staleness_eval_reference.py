"""Staleness-stratified eval: does each arm give the CURRENT answer or a superseded one?

Unlike the gold-fact eval (facts never expire), every question here has an answer that
CHANGED over Flink's history; both the old and new forms exist in the 5-year corpus, so
a wide index contains the conflict. We score the ANSWER (not the retrieved context):

  deterministic:  regex match for currentPatterns / stalePatterns on the answer text
  judge:          classify the answer's RECOMMENDATION as
                  CURRENT | STALE | BOTH (no clear pick) | NEITHER
                  (mentioning the old form while flagging it deprecated counts CURRENT)

Usage:
  python scripts/staleness_eval.py --arms vector=http://localhost:8101 \
      llm-only=http://localhost:8105 --tag 1mo-r1 \
      [--questions eval/questions-staleness.json] [--out results]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone

import httpx

sys.path.insert(0, ".")
from ragbench.config import load_config  # noqa: E402
from ragbench.cost import CostMeter  # noqa: E402
from ragbench.llm import LLM  # noqa: E402

JUDGE_SYS = (
    "You grade whether an answer about Apache Flink recommends the CURRENT approach or a "
    "SUPERSEDED one. You are given the question, the current answer, the superseded answer, "
    "and what changed. Classify the answer's effective recommendation as exactly one of:\n"
    "CURRENT  - it recommends the current approach (mentioning the old one as deprecated/"
    "historical is fine)\n"
    "STALE    - it recommends the superseded approach as the way to do it, without flagging "
    "that it is deprecated/replaced\n"
    "BOTH     - it presents both without a clear recommendation\n"
    "NEITHER  - it does not answer, or recommends something else entirely\n"
    'Reply with JSON only: {"label": "...", "reason": "<one sentence>"}'
)


def judge(llm, meter, q, answer):
    user = (
        f"Question: {q['question']}\n"
        f"CURRENT answer: {q['current']}\n"
        f"SUPERSEDED answer: {q['stale']}\n"
        f"What changed: {q['changed']}\n\n"
        f"Answer to grade:\n{answer}"
    )
    msg = llm.chat(
        [{"role": "system", "content": JUDGE_SYS}, {"role": "user", "content": user}], meter
    )
    txt = (msg.content or "").strip()
    m = re.search(r'"label"\s*:\s*"(CURRENT|STALE|BOTH|NEITHER)"', txt)
    label = m.group(1) if m else "NEITHER"
    return label, txt[:300]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arms", nargs="+", required=True, help="name=url pairs")
    ap.add_argument("--questions", default="eval/questions-staleness.json")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    qs = json.load(open(args.questions))["questions"]
    cfg = load_config()
    import dataclasses

    jllm = LLM(dataclasses.replace(cfg, chat_model=cfg.judge_model))
    jmeter = CostMeter(label="judge:staleness")

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "tag": args.tag, "arms": {}}
    for pair in args.arms:
        name, url = pair.split("=", 1)
        print(f"=== {name} @ {url} ===", file=sys.stderr)
        detail = {}
        counts = {"CURRENT": 0, "STALE": 0, "BOTH": 0, "NEITHER": 0}
        det_counts = {"cur_hit": 0, "stale_hit": 0}
        usd = 0.0
        for q in qs:
            t0 = time.perf_counter()
            try:
                with httpx.Client(timeout=300) as client:
                    r = client.post(url.rstrip("/") + "/answer", json={"question": q["question"]})
                    r.raise_for_status()
                    data = r.json()
                ans = data.get("answer", "")
                usd_q = (data.get("cost") or {}).get("usd", 0.0)
            except Exception as e:
                ans, usd_q = f"(arm failed: {e})", 0.0
            secs = time.perf_counter() - t0
            cur_hit = any(re.search(p, ans) for p in q["currentPatterns"])
            stale_hit = any(re.search(p, ans) for p in q["stalePatterns"])
            label, jraw = judge(jllm, jmeter, q, ans)
            counts[label] += 1
            det_counts["cur_hit"] += cur_hit
            det_counts["stale_hit"] += stale_hit
            usd += usd_q
            detail[q["id"]] = {
                "answer": ans,
                "label": label,
                "cur_regex": cur_hit,
                "stale_regex": stale_hit,
                "usd": round(usd_q, 6),
                "secs": round(secs, 2),
                "judge_raw": jraw,
            }
            print(
                f"  [{q['id']}] {label:7s} cur_re={int(cur_hit)} stale_re={int(stale_hit)} "
                f"{secs:.1f}s ${usd_q:.4f}",
                file=sys.stderr,
            )
        n = len(qs)
        out["arms"][name] = {
            "n": n,
            "current_rate": round(counts["CURRENT"] / n, 4),
            "stale_rate": round(counts["STALE"] / n, 4),
            "both_rate": round(counts["BOTH"] / n, 4),
            "neither_rate": round(counts["NEITHER"] / n, 4),
            "cur_regex_rate": round(det_counts["cur_hit"] / n, 4),
            "stale_regex_rate": round(det_counts["stale_hit"] / n, 4),
            "usd_total": round(usd, 4),
            "detail": detail,
        }
        a = out["arms"][name]
        print(
            f"  => current={a['current_rate']:.2f} stale={a['stale_rate']:.2f} "
            f"both={a['both_rate']:.2f} neither={a['neither_rate']:.2f}",
            file=sys.stderr,
        )

    import os

    os.makedirs(args.out, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = os.path.join(args.out, f"staleness-{stamp}-{args.tag}.json")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
