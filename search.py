from sentence_transformers import SentenceTransformer
import chromadb
import requests as req_lib
import re
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

print("Loading embedding model (BGE-M3)... this may take a minute on first run.")
embedder = SentenceTransformer("BAAI/bge-m3")

client = chromadb.PersistentClient(path=r"D:\FactoryKA\chroma_db")
collection = client.get_or_create_collection(name="factory_docs")


def embed_text(text):
    return embedder.encode(text).tolist()


def add_chunk(chunk_id, text, metadata):
    embedding = embed_text(text)
    collection.add(
        ids=[chunk_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[metadata]
    )


def search_chunks(query, n_results=3):
    query_embedding = embed_text(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )
    return results


def format_source(meta):
    page_info = meta.get('page_number')
    source_file = meta.get('source_file')
    if isinstance(page_info, (int, float)):
        return f"{source_file} (page {page_info})"
    else:
        return f"{source_file} ({page_info})"


def detect_language(text):
    try:
        lang = detect(text)
        return "Japanese" if lang == "ja" else "English"
    except Exception:
        return "English"


def _strip_source_mentions(text):
    """
    Safety net: even with prompt instructions, the model can still leak
    "SOURCE 1", "SOURCE 3", etc. into the visible answer. This removes
    any such mentions that slipped through, as a final cleanup pass.
    """
    return re.sub(r"\bSOURCE\s*\d+\b", "the source material", text, flags=re.IGNORECASE)


def generate_answer(query, n_results=5):
    """
    Full RAG pipeline with:
    - code-based language detection
    - single-source citation (model states which source(s) it actually used)
    - clarification-seeking behavior for THREE cases (ambiguous term,
      underspecified question, multiple conflicting product tables)
    - anti-over-interpretation guard for safety-relevant claims
    - a code-level cleanup pass that strips any "SOURCE N" text that
      leaks into the visible answer despite the prompt instruction
    """
    results = search_chunks(query, n_results=n_results)

    docs = results['documents'][0]
    metas = results['metadatas'][0]
    all_sources = [format_source(m) for m in metas]

    labeled_context = []
    for i, doc in enumerate(docs):
        labeled_context.append(f"[SOURCE {i+1}: {all_sources[i]}]\n{doc}")
    context = "\n\n---\n\n".join(labeled_context)

    detected_lang = detect_language(query)

    if detected_lang == "Japanese":
        language_instruction = (
            "You MUST answer entirely in natural, fluent Japanese. "
            "Do NOT use any English words, Chinese characters, or mixed-language terms. "
            "Translate all technical terms into standard Japanese katakana "
            "(e.g. fuse -> ヒューズ, relay -> リレー, conveyor -> コンベア). "
            "If you do not know the correct Japanese term, use a simple Japanese description instead of an English word."
        )
    else:
        language_instruction = (
            "You MUST answer entirely in English. Do NOT use any Japanese or Chinese characters."
        )

    prompt = f"""Answer the question using ONLY the context below. Each piece of context is labeled with a SOURCE number.

{language_instruction}

CRITICAL RULE - NEVER VIOLATE THIS: Never write the word "SOURCE" or any source number (like "SOURCE 1", "SOURCE 3") anywhere in your answer text. If you need to refer to different pieces of context while comparing conflicting values, describe them by content instead (e.g. "one table shows...", "another entry lists...", "a different relay type states...") — never by their SOURCE number. Source numbers are ONLY allowed in the final USED SOURCES line, nowhere else.

IMPORTANT - ASK FOR CLARIFICATION when needed, in THREE situations. In all three, do NOT guess a single value, do NOT average or blend numbers from different places, and do NOT list every conflicting value as if that were an answer — instead give a SHORT answer that says clarification is needed, and ask a specific question:

1. AMBIGUOUS TERM: a short term, code, or abbreviation could mean more than one different thing across the context. Name the possibilities and ask which is meant.

2. UNDERSPECIFIED QUESTION: the topic is clear, but the source has multiple values depending on a parameter the question didn't give (a quantity, size, model, category). Name the missing parameter.

3. MULTIPLE CONFLICTING PRODUCT TABLES: the context contains different tables or sections, belonging to different products, models, classes, or types, that each give a different value for what looks like the same question. Do not try to reconcile, average, or list all the conflicting numbers. Instead, briefly state that the answer depends on which product/type is meant, name 1-3 of the products/types you noticed (by their description, never by SOURCE number), and ask the user to specify. Keep this answer SHORT - a sentence or two plus the question, not a breakdown of every value found.

IMPORTANT - ACCURACY: State only what the source text explicitly says. Do NOT add conclusions, guarantees, or interpretations that go beyond the literal wording of the source — this is especially critical for safety-related statements.

Write your complete answer FIRST. Then, as the VERY LAST line of your response (after the answer, never before it), write exactly which source(s) you used, in this exact format:
USED SOURCES: 1, 3

If the answer isn't in the context, write your explanation first (in {detected_lang}), then end with:
USED SOURCES: none

Only list source numbers you actually relied on.

Context:
{context}

Question: {query}

Answer:"""

    response = req_lib.post("http://localhost:11434/api/generate", json={
        "model": "qwen2.5:7b-instruct-q4_K_M",
        "prompt": prompt,
        "stream": False
    })

    raw_answer = response.json()["response"]

    used_ids = []
    match = re.search(r"USED SOURCES:\s*(.+)", raw_answer, re.IGNORECASE)
    if match:
        ids_text = match.group(1)
        if "none" not in ids_text.lower():
            used_ids = [int(x.strip()) for x in re.findall(r"\d+", ids_text)]
        before = raw_answer[:match.start()].strip()
        after = raw_answer[match.end():].strip()
        answer_clean = before if before else after
    else:
        answer_clean = raw_answer.strip()

    if not answer_clean:
        answer_clean = "I don't have enough information to answer this."

    answer_clean = _strip_source_mentions(answer_clean)

    if used_ids:
        used_sources = list(dict.fromkeys(
            [all_sources[i - 1] for i in used_ids if 0 < i <= len(all_sources)]
        ))
    else:
        used_sources = []

    return {
        "answer": answer_clean,
        "sources": used_sources if used_sources else ["No specific source cited"],
        "detected_language": detected_lang,
        "all_retrieved_sources": all_sources
    }


if __name__ == "__main__":
    print(f"Total chunks in store: {collection.count()}")

    query = "What is the shipping weight based on the number of poles?"
    print(f"\nRunning 3 times to check consistency of clarification behavior:\n")
    for i in range(3):
        result = generate_answer(query)
        print(f"--- Run {i+1} ---")
        print(f"Answer: {result['answer']}")
        print(f"Sources: {result['sources']}\n")