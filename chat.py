from search import generate_answer

print("=" * 60)
print("Factory Knowledge Assistant — Phase 1 Q&A")
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