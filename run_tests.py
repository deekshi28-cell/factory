import json
from search import generate_answer

def run_automatic_tests():
    with open(r"D:\FactoryKA\test_questions.json", "r", encoding="utf-8") as f:
        questions = json.load(f)

    results = []
    passed = 0

    for q in questions:
        result = generate_answer(q["question"])
        
        # simple check: does the expected source appear in the actual sources?
        source_match = any(
            str(q.get("expected_source", "")).split(",")[0].strip().lower() in s.lower()
            for s in result["sources"]
        ) if q.get("expected_source") else True

        print(f"[{q['id']}] {q['question'][:60]}")
        print(f"  Actual: {result['answer'][:150]}")
        print(f"  Sources: {result['sources']}")
        print(f"  Source match: {source_match}\n")

        if source_match:
            passed += 1

        results.append({
            "id": q["id"],
            "question": q["question"],
            "actual_answer": result["answer"],
            "actual_sources": result["sources"],
            "source_match": source_match
        })

    print(f"\n{'='*50}")
    print(f"TOTAL: {len(questions)} | Source-matched: {passed} ({passed/len(questions)*100:.1f}%)")

    with open(r"D:\FactoryKA\automatic_test_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_automatic_tests()