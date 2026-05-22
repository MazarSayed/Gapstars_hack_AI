"""
Eval runner — scores agent outputs against golden_evals.json using LLM-as-judge.

Usage:
    cd backend
    uv run python evals/eval_runner.py [--ids meeting_001 meeting_002 ...]
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

# ── path setup so we can import from backend/ ──────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from google import genai
from google.genai import types

from utils import make_client, parse_json, DEFAULT_MODEL
from agents.meeting_summarizer import stream_meeting_summarizer
from agents.action_item_agent import stream_action_item_agent
from metrics import (
    METRICS,
    SUMMARY_METRICS,
    ACTION_METRICS,
    MAX_SCORE,
    MAX_TOTAL,
    Metric,
    Target,
)

# ── constants ───────────────────────────────────────────────────────────────
EVALS_DIR = Path(__file__).parent
GOLDEN_PATH = EVALS_DIR / "golden_evals.json"
TRANSCRIPT_SEARCH_DIRS = [
    EVALS_DIR,
    BACKEND_DIR / "example" / "transcripts",
]
JUDGE_MODEL = DEFAULT_MODEL

JUDGE_SYSTEM = """\
You are an expert evaluator for AI-generated meeting summaries and action-item reports.

You will receive:
  • A METRIC with a 1–5 rubric
  • The EXPECTED output (golden eval ground truth)
  • The ACTUAL output produced by the agent under test

Score the ACTUAL output on the metric and provide a one-sentence reasoning.

Respond ONLY with valid JSON — no markdown fences:
{"score": <integer 1–5>, "reasoning": "<one concise sentence>"}
"""


# ── helpers ──────────────────────────────────────────────────────────────────

def find_transcript(source: str) -> Path:
    for d in TRANSCRIPT_SEARCH_DIRS:
        p = d / source
        if p.exists():
            return p
    raise FileNotFoundError(
        f"Transcript '{source}' not found in {[str(d) for d in TRANSCRIPT_SEARCH_DIRS]}"
    )


async def collect_stream(agent_fn, client: genai.Client, transcript: str) -> dict:
    """Drain an agent's streaming generator and parse the accumulated JSON."""
    chunks: list[str] = []
    async for chunk in agent_fn(client, transcript):
        chunks.append(chunk)
    return parse_json("".join(chunks))


async def judge(
    client: genai.Client,
    metric: Metric,
    actual: dict,
    expected: dict,
) -> dict[str, Any]:
    prompt = (
        f"METRIC: {metric.name}\n"
        f"DESCRIPTION: {metric.description}\n\n"
        f"RUBRIC:\n{metric.rubric_text()}\n\n"
        f"EXPECTED OUTPUT (golden):\n{json.dumps(expected, indent=2)}\n\n"
        f"ACTUAL OUTPUT (agent):\n{json.dumps(actual, indent=2)}\n"
    )
    config = types.GenerateContentConfig(
        system_instruction=JUDGE_SYSTEM,
        response_mime_type="application/json",
    )
    response = await client.aio.models.generate_content(
        model=JUDGE_MODEL,
        contents=prompt,
        config=config,
    )
    try:
        return parse_json(response.text)
    except Exception:
        return {"score": 0, "reasoning": f"Judge parse error: {response.text[:120]}"}


# ── per-meeting evaluation ───────────────────────────────────────────────────

async def evaluate_meeting(
    client: genai.Client,
    entry: dict,
) -> dict:
    meeting_id = entry["id"]
    source = entry["source"]
    transcript = find_transcript(source).read_text()
    expected = entry["expected"]

    print(f"  [{meeting_id}] running agents … ", end="", flush=True)
    t0 = time.monotonic()
    actual_summary, actual_action = await asyncio.gather(
        collect_stream(stream_meeting_summarizer, client, transcript),
        collect_stream(stream_action_item_agent, client, transcript),
    )
    print(f"done ({time.monotonic()-t0:.1f}s)")

    print(f"  [{meeting_id}] judging {len(METRICS)} metrics … ", end="", flush=True)
    t1 = time.monotonic()

    async def score_one(metric: Metric) -> tuple[str, dict]:
        if metric.target == Target.summary:
            actual_sec = actual_summary
            expected_sec = expected["summary"]
        else:
            actual_sec = actual_action
            expected_sec = expected["action_report"]
        result = await judge(client, metric, actual_sec, expected_sec)
        return metric.name, result

    pairs = await asyncio.gather(*[score_one(m) for m in METRICS])
    scores = dict(pairs)
    print(f"done ({time.monotonic()-t1:.1f}s)")

    return {
        "id": meeting_id,
        "title": entry["meeting_title"],
        "scores": scores,
    }


# ── output formatting ────────────────────────────────────────────────────────

_BAR_FULL = "█"
_BAR_EMPTY = "░"

def _bar(score: int, max_score: int = MAX_SCORE) -> str:
    return _BAR_FULL * score + _BAR_EMPTY * (max_score - score)


def print_results(results: list[dict]) -> None:
    sep_thin = "─" * 80
    sep_thick = "═" * 80

    for r in results:
        print(f"\n{sep_thin}")
        print(f"  {r['id'].upper()}  │  {r['title']}")
        print(sep_thin)

        meeting_total = 0

        print("  SUMMARY METRICS")
        for m in SUMMARY_METRICS:
            entry = r["scores"].get(m.name, {"score": 0, "reasoning": "n/a"})
            score = entry["score"]
            meeting_total += score
            reasoning = entry["reasoning"][:72]
            print(
                f"    {m.name:<36} {_bar(score)}  {score}/{MAX_SCORE}"
                f"\n      ↳ {reasoning}"
            )

        print("  ACTION REPORT METRICS")
        for m in ACTION_METRICS:
            entry = r["scores"].get(m.name, {"score": 0, "reasoning": "n/a"})
            score = entry["score"]
            meeting_total += score
            reasoning = entry["reasoning"][:72]
            print(
                f"    {m.name:<36} {_bar(score)}  {score}/{MAX_SCORE}"
                f"\n      ↳ {reasoning}"
            )

        pct = meeting_total / MAX_TOTAL * 100
        print(f"\n  MEETING TOTAL  {meeting_total}/{MAX_TOTAL}  ({pct:.0f}%)")

    # ── aggregate ────────────────────────────────────────────────────────────
    print(f"\n\n{sep_thick}")
    print("  AGGREGATE RESULTS")
    print(sep_thick)

    grand_avg = 0.0
    for m in METRICS:
        scores_list = [
            r["scores"][m.name]["score"]
            for r in results
            if m.name in r["scores"]
        ]
        if not scores_list:
            continue
        avg = sum(scores_list) / len(scores_list)
        grand_avg += avg
        filled = round(avg)
        tag = " (summary)" if m.target == Target.summary else " (actions)"
        print(f"  {m.name:<36} {_bar(filled)}  {avg:.2f}/{MAX_SCORE}{tag}")

    pct = grand_avg / MAX_TOTAL * 100
    print(f"\n  OVERALL AVERAGE  {grand_avg:.1f}/{MAX_TOTAL}  ({pct:.0f}%)")
    print(sep_thick)


# ── entry point ──────────────────────────────────────────────────────────────

async def main(filter_ids: list[str] | None = None) -> None:
    golden = json.loads(GOLDEN_PATH.read_text())

    if filter_ids:
        golden = [e for e in golden if e["id"] in filter_ids]
        if not golden:
            print(f"No entries matched ids: {filter_ids}")
            sys.exit(1)

    client = make_client()

    print(f"\nRunning evals on {len(golden)} meeting(s) …\n")
    results = []
    for entry in golden:
        try:
            result = await evaluate_meeting(client, entry)
            results.append(result)
        except Exception as exc:
            print(f"  ERROR on {entry['id']}: {exc}")

    if results:
        print_results(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run golden evals with LLM-as-judge")
    parser.add_argument(
        "--ids",
        nargs="*",
        metavar="ID",
        help="Subset of meeting IDs to evaluate (e.g. meeting_001 meeting_002). "
             "Omit to run all.",
    )
    args = parser.parse_args()
    asyncio.run(main(filter_ids=args.ids))
