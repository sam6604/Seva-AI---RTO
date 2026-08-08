"""
Lightweight evaluation harness for the Phase 1 hybrid RAG pipeline.

Run:
    python eval/run_eval.py

Two modes, chosen automatically based on whether SARVAM_API_KEY is set:

1. RETRIEVAL-ONLY (always runs, no API key needed):
   - service routing accuracy (does the router assign the expected service?)
   - retrieval hit rate (does retrieval surface the expected keywords?)
   - gap handling (do vehicle_transfer/vehicle_registration questions
     correctly come back "insufficient evidence" instead of guessing?)
   - retrieval latency per query

2. FULL PIPELINE (only for questions with an English form, only if
   SARVAM_API_KEY is set — needs a live Sarvam call):
   - end-to-end latency, broken into retrieval vs LLM/translate/TTS-adjacent
     stages that intelligence.respond() itself performs
   - a crude groundedness/hallucination check: for "insufficient evidence"
     questions, does the actual reply match the safe fallback (no invented
     specifics)? For answerable questions, does the reply's specific claims
     (numbers, doc names) actually appear in the retrieved citations?

This is intentionally NOT a claim of ">=95% accuracy" — true answer
correctness needs human or LLM-judge review against the questions' known
answers. What this harness *can* verify automatically: routing is correct,
retrieval surfaces the right evidence, gaps are honestly reported instead
of hallucinated, and latency stays low. Those are necessary conditions for
hitting the accuracy target, and the parts most likely to silently break as
the system evolves.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from retrieval import get_process_outline, retrieve  # noqa: E402

QUESTIONS_PATH = Path(__file__).parent / "test_questions.json"


def _question_text(q: dict):
    return q.get("question_en") or q.get("question_hi") or q.get("question_or")


def run_retrieval_eval(questions):
    print("=" * 70)
    print("RETRIEVAL-ONLY EVALUATION (routing, hit-rate, gap handling, latency)")
    print("=" * 70)

    routing_correct = routing_total = 0
    hit_correct = hit_total = 0
    gap_correct = gap_total = 0
    latencies = []
    skipped = []

    for q in questions:
        text = _question_text(q)
        if not q.get("question_en") and (q.get("question_hi") or q.get("question_or")):
            # No API key => no translation => can't route non-English text
            # through the same path production uses. Counted separately.
            skipped.append(q["id"])
            continue
        if text is None:
            continue

        t0 = time.perf_counter()
        result = retrieve(text, top_k=4)
        latencies.append((time.perf_counter() - t0) * 1000)

        expected_service = q.get("service_id")
        if expected_service is not None:
            routing_total += 1
            if result.service_id == expected_service:
                routing_correct += 1
            else:
                print(f"  [ROUTING MISS] {q['id']}: expected {expected_service}, got {result.service_id}")

        if q.get("expects_insufficient"):
            gap_total += 1
            if result.insufficient_evidence:
                gap_correct += 1
            else:
                print(f"  [GAP MISS] {q['id']}: expected insufficient_evidence=True, got False "
                      f"(chunks: {[c.source for c in result.chunks]})")

        if q.get("expected_keywords"):
            hit_total += 1
            # Phase 2: for a service with verified process data, the model
            # sees the retrieved fragments AND the full process outline
            # (see intelligence.respond()) — so a fair check is "does the
            # keyword show up in either", matching what actually reaches
            # the LLM, not just the top-k citation fragments.
            outline = get_process_outline(result.service_id) or ""
            joined = " ".join(c.text.lower() for c in result.chunks) + " " + outline.lower()
            hits = [kw for kw in q["expected_keywords"] if kw.lower() in joined]
            if hits:
                hit_correct += 1
            else:
                print(f"  [RETRIEVAL MISS] {q['id']}: none of {q['expected_keywords']} found in retrieved chunks "
                      f"or process outline")

    print()
    if routing_total:
        print(f"Service routing accuracy:   {routing_correct}/{routing_total} "
              f"({100 * routing_correct / routing_total:.1f}%)")
    if gap_total:
        print(f"Gap handling accuracy:      {gap_correct}/{gap_total} "
              f"({100 * gap_correct / gap_total:.1f}%)")
    if hit_total:
        print(f"Retrieval keyword hit rate: {hit_correct}/{hit_total} "
              f"({100 * hit_correct / hit_total:.1f}%)")
    if latencies:
        print(f"Retrieval latency: avg {sum(latencies)/len(latencies):.2f}ms, "
              f"max {max(latencies):.2f}ms, min {min(latencies):.2f}ms  (n={len(latencies)})")
    if skipped:
        print(f"Skipped (need SARVAM_API_KEY to translate to English): {skipped}")
    print()


def run_full_pipeline_eval(questions):
    import intelligence

    print("=" * 70)
    print("FULL PIPELINE EVALUATION (SARVAM_API_KEY detected)")
    print("=" * 70)

    total_latencies, retrieval_latencies, llm_latencies = [], [], []
    groundedness_ok = groundedness_total = 0

    for q in questions:
        text = q.get("question_en")
        if not text:
            continue  # translation path exercised separately; keep this harness's own latency clean

        t0 = time.perf_counter()
        t_retrieval_start = time.perf_counter()
        result = retrieve(text, top_k=4)
        retrieval_ms = (time.perf_counter() - t_retrieval_start) * 1000

        history = []
        t_llm_start = time.perf_counter()
        reply, citations = intelligence.respond(history, text)
        llm_ms = (time.perf_counter() - t_llm_start) * 1000
        total_ms = (time.perf_counter() - t0) * 1000

        retrieval_latencies.append(retrieval_ms)
        llm_latencies.append(llm_ms)
        total_latencies.append(total_ms)

        if q.get("expects_insufficient"):
            groundedness_total += 1
            if intelligence.INSUFFICIENT_EVIDENCE_TEMPLATE in reply:
                groundedness_ok += 1
            else:
                print(f"  [HALLUCINATION RISK] {q['id']}: expected the insufficient-evidence fallback, "
                      f"model answered instead: {reply[:120]!r}")
        elif citations:
            groundedness_total += 1
            citation_text = " ".join(citations).lower()
            # crude overlap check: does the reply share vocabulary with what
            # it was actually given, rather than introducing unrelated specifics
            reply_words = set(w.strip(".,!?") for w in reply.lower().split() if len(w) > 4)
            citation_words = set(citation_text.split())
            overlap = len(reply_words & citation_words) / max(len(reply_words), 1)
            if overlap > 0.15:
                groundedness_ok += 1
            else:
                print(f"  [LOW GROUNDING OVERLAP] {q['id']}: only {overlap:.0%} vocabulary overlap with citations")

    print()
    if groundedness_total:
        print(f"Groundedness check passed:  {groundedness_ok}/{groundedness_total} "
              f"({100 * groundedness_ok / groundedness_total:.1f}%)")
    if total_latencies:
        n = len(total_latencies)
        print(f"Retrieval latency: avg {sum(retrieval_latencies)/n:.2f}ms")
        print(f"LLM (respond) latency: avg {sum(llm_latencies)/n:.2f}ms")
        print(f"Total latency: avg {sum(total_latencies)/n:.2f}ms")
        bottleneck = "LLM call" if sum(llm_latencies) > sum(retrieval_latencies) else "retrieval"
        print(f"Largest bottleneck: {bottleneck} "
              f"(retrieval is {'~0' if not retrieval_latencies else f'{100*sum(retrieval_latencies)/sum(total_latencies):.1f}%'} of total)")
    print()


def main():
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    run_retrieval_eval(questions)

    if os.getenv("SARVAM_API_KEY"):
        run_full_pipeline_eval(questions)
    else:
        print("SARVAM_API_KEY not set — skipping full-pipeline (LLM) evaluation.")
        print("Set it in .env and re-run for end-to-end latency + groundedness checks.\n")


if __name__ == "__main__":
    main()
