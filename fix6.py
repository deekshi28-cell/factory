from search import search_chunks

results = search_chunks("What is the shipping weight based on the number of poles?", n_results=5)
for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
    print(f"--- {meta['source_file']} ({meta.get('page_number')}) ---")
    print(doc[:200])
    print()