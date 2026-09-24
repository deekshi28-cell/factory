"""
Measures how long each question takes to answer, against the 15-second target.

Usage:
    python benchmark_latency.py              # first 20 questions from test_questions.json
    python benchmark_latency.py --limit 99   # all questions

Prints each question's time, then: median, 95th percentile, slowest, share under target,
and the average time spent in each step (search, model load, reading the prompt, writing the answer).
"""
import argparse
import json
import os
import statistics

from search import generate_answer, warm_up, format_timings, TARGET_SECONDS, LLM_MODEL, N_RESULTS, LLM_MAX_TOKENS


def percentile(values, pct):
    ordered = sorted(values)
    idx = min(len(ordered) - 1, round(pct / 100 * (len(ordered) - 1)))
    return ordered[idx]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="number of test questions to run")
    parser.add_argument("--questions", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_questions.json"))
    args = parser.parse_args()

    with open(args.questions, "r", encoding="utf-8") as f:
        questions = json.load(f)[:args.limit]

    print(f"Model: {LLM_MODEL} | chunks per question: {N_RESULTS} | max answer tokens: {LLM_MAX_TOKENS}")
    print(f"Warm-up: {warm_up():.1f}s\n")

    runs = []
    for q in questions:
        t = generate_answer(q["question"])["timings"]
        runs.append(t)
        flag = "OK  " if t["total_s"] <= TARGET_SECONDS else "SLOW"
        print(f"[{flag}] #{q['id']} {q['question'][:50]!r}\n        {format_timings(t)}")

    totals = [t["total_s"] for t in runs]
    under = sum(1 for x in totals if x <= TARGET_SECONDS)

    def avg(key):
        return statistics.mean(t[key] for t in runs)

    print("\n" + "=" * 60)
    print(f"Questions: {len(runs)} | under {TARGET_SECONDS}s: {under}/{len(runs)} ({under / len(runs) * 100:.0f}%)")
    print(f"Median: {statistics.median(totals):.1f}s | 95th percentile: {percentile(totals, 95):.1f}s | slowest: {max(totals):.1f}s")
    print(f"Average per step: search {avg('retrieval_s'):.1f}s | model load {avg('load_s'):.1f}s | "
          f"read prompt {avg('prompt_s'):.1f}s ({avg('prompt_tokens'):.0f} tokens) | "
          f"write answer {avg('output_s'):.1f}s ({avg('output_tokens'):.0f} tokens)")
    if avg("output_s") > 0:
        print(f"Generation speed: {avg('output_tokens') / avg('output_s'):.1f} tokens/s")


if __name__ == "__main__":
    main()
