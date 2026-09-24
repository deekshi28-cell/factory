from search import generate_answer, warm_up, format_timings, TARGET_SECONDS, LLM_MODEL

print("=" * 60)
print("Factory Knowledge Assistant — Phase 1 Q&A")
print("=" * 60)

# load the LLM into memory before the first question, so it isn't slowed by model loading
print(f"Warming up {LLM_MODEL}...")
try:
    print(f"Ready (warm-up took {warm_up():.1f}s).")
except Exception as e:
    print(f"Warm-up failed ({e}). Is Ollama running? Continuing anyway.")

print("Type your question and press Enter.")
print("Type 'exit' or 'quit' to stop.")
print("=" * 60)

while True:
    query = input("\nYour question: ").strip()

    if query.lower() in ("exit", "quit"):
        print("Goodbye!")
        break

    if not query:
        continue

    print("Searching and generating answer...")
    result = generate_answer(query)

    print(f"\nAnswer: {result['answer']}")
    print(f"Sources: {', '.join(result['sources'])}")

    t = result["timings"]
    status = "OK" if t["total_s"] <= TARGET_SECONDS else f"SLOW - over {TARGET_SECONDS}s target"
    print(f"[{status}] {format_timings(t)}")
