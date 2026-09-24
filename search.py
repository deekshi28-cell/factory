from sentence_transformers import SentenceTransformer
import chromadb
import requests as req_lib
import os
import re
import time
from langdetect import detect, DetectorFactory

DetectorFactory.seed = 0

# Settings - defaults match the original setup, override with environment variables if needed
CHROMA_DIR = os.environ.get("FACTORY_CHROMA_DIR", r"D:\FactoryKA\chroma_db")
OLLAMA_URL = os.environ.get("FACTORY_OLLAMA_URL", "http://localhost:11434")
LLM_MODEL = os.environ.get("FACTORY_LLM_MODEL", "qwen2.5:7b-instruct-q4_K_M")
N_RESULTS = int(os.environ.get("FACTORY_N_RESULTS", "5"))

# Speed settings (target: every answer in under 15 seconds)
# - keep_alive: keep the LLM loaded in memory between questions. Ollama's default
#   unloads it after 5 idle minutes, and reloading a 7B model costs 5-20 seconds.
# - num_ctx: fixed context size. 5 chunks + instructions is ~2000-3000 tokens,
#   so 4096 fits without silent truncation, and a fixed value avoids model reloads.
# - num_predict: upper limit on answer length - generation time grows with every token.
LLM_KEEP_ALIVE = os.environ.get("FACTORY_LLM_KEEP_ALIVE", "60m")
LLM_NUM_CTX = int(os.environ.get("FACTORY_LLM_NUM_CTX", "4096"))
LLM_MAX_TOKENS = int(os.environ.get("FACTORY_LLM_MAX_TOKENS", "400"))
LLM_TIMEOUT = int(os.environ.get("FACTORY_LLM_TIMEOUT", "120"))
TARGET_SECONDS = 15

print("Loading embedding model (BGE-M3)... this may take a minute on first run.")
embedder = SentenceTransformer("BAAI/bge-m3")

client = chromadb.PersistentClient(path=CHROMA_DIR)
collection = client.get_or_create_collection(name="factory_docs")

# one HTTP connection reused for every Ollama call
http = req_lib.Session()


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


# Fixed instructions, identical for every question. They come FIRST in the prompt so
# Ollama can reuse its cached work for this prefix (prompt caching) instead of
# re-reading ~700 tokens of rules on every question. Everything that changes per
# question (context, language, question) comes after it.
PROMPT_RULES = """Answer the question using ONLY the context below. Each piece of context is labeled with a SOURCE number.

CRITICAL RULE - NEVER VIOLATE THIS: Never write the word "SOURCE" or any source number (like "SOURCE 1", "SOURCE 3") anywhere in your answer text. If you need to refer to different pieces of context while comparing conflicting values, describe them by content instead (e.g. "one table shows...", "another entry lists...", "a different relay type states...") — never by their SOURCE number. Source numbers are ONLY allowed in the final USED SOURCES line, nowhere else.

IMPORTANT - ASK FOR CLARIFICATION when needed, in THREE situations. In all three, do NOT guess a single value, do NOT average or blend numbers from different places, and do NOT list every conflicting value as if that were an answer — instead give a SHORT answer that says clarification is needed, and ask a specific question:

1. AMBIGUOUS TERM: a short term, code, or abbreviation could mean more than one different thing across the context. Name the possibilities and ask which is meant.

2. UNDERSPECIFIED QUESTION: the topic is clear, but the source has multiple values depending on a parameter the question didn't give (a quantity, size, model, category). Name the missing parameter.

3. MULTIPLE CONFLICTING PRODUCT TABLES: the context contains different tables or sections, belonging to different products, models, classes, or types, that each give a different value for what looks like the same question. Do not try to reconcile, average, or list all the conflicting numbers. Instead, briefly state that the answer depends on which product/type is meant, name 1-3 of the products/types you noticed (by their description, never by SOURCE number), and ask the user to specify. Keep this answer SHORT - a sentence or two plus the question, not a breakdown of every value found.

IMPORTANT - ACCURACY: State only what the source text explicitly says. Do NOT add conclusions, guarantees, or interpretations that go beyond the literal wording of the source — this is especially critical for safety-related statements.

IMPORTANT - BE CONCISE: Answer directly in a few sentences or a short list. Do not repeat the question or add background that was not asked for.

Write your complete answer FIRST. Then, as the VERY LAST line of your response (after the answer, never before it), write exactly which source(s) you used, in this exact format:
USED SOURCES: 1, 3

If the answer isn't in the context, write your explanation first (in the answer language given below), then end with:
USED SOURCES: none

Only list source numbers you actually relied on.

Context:
"""


def _language_instruction(detected_lang):
    if detected_lang == "Japanese":
        return (
            "You MUST answer entirely in natural, fluent Japanese. "
            "Do NOT use any English words, Chinese characters, or mixed-language terms. "
            "Translate all technical terms into standard Japanese katakana "
            "(e.g. fuse -> ヒューズ, relay -> リレー, conveyor -> コンベア). "
            "If you do not know the correct Japanese term, use a simple Japanese description instead of an English word."
        )
    return "You MUST answer entirely in English. Do NOT use any Japanese or Chinese characters."


def build_prompt(query, context, detected_lang):
    return f"""{PROMPT_RULES}{context}

ANSWER LANGUAGE: {_language_instruction(detected_lang)}

Question: {query}

Answer:"""


def call_llm(prompt, max_tokens=LLM_MAX_TOKENS):
    """Sends one prompt to Ollama and returns (answer_text, ollama_stats_dict)."""
    response = http.post(f"{OLLAMA_URL}/api/generate", json={
        "model": LLM_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": LLM_KEEP_ALIVE,
        "options": {
            "num_ctx": LLM_NUM_CTX,
            "num_predict": max_tokens,
        }
    }, timeout=LLM_TIMEOUT)
    response.raise_for_status()
    data = response.json()

    # Ollama reports its durations in nanoseconds
    ns = 1e9
    stats = {
        "load_s": data.get("load_duration", 0) / ns,
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "prompt_s": data.get("prompt_eval_duration", 0) / ns,
        "output_tokens": data.get("eval_count", 0),
        "output_s": data.get("eval_duration", 0) / ns,
    }
    return data.get("response", ""), stats


def warm_up():
    """
    Loads the LLM into memory and pre-caches the fixed instruction prefix,
    so the user's FIRST question is as fast as the rest. Also warms up the
    embedding model. Call once at startup (chat.py does this).
    """
    t0 = time.perf_counter()
    embed_text("warm up")
    call_llm(build_prompt("warm up", "", "English"), max_tokens=1)
    return time.perf_counter() - t0


def generate_answer(query, n_results=N_RESULTS):
    """
    Full RAG pipeline with:
    - code-based language detection
    - single-source citation (model states which source(s) it actually used)
    - clarification-seeking behavior for THREE cases (ambiguous term,
      underspecified question, multiple conflicting product tables)
    - anti-over-interpretation guard for safety-relevant claims
    - a code-level cleanup pass that strips any "SOURCE N" text that
      leaks into the visible answer despite the prompt instruction
    - timing breakdown for each step (returned under "timings")
    """
    t_start = time.perf_counter()
    results = search_chunks(query, n_results=n_results)

    docs = results['documents'][0]
    metas = results['metadatas'][0]
    all_sources = [format_source(m) for m in metas]

    labeled_context = []
    for i, doc in enumerate(docs):
        labeled_context.append(f"[SOURCE {i+1}: {all_sources[i]}]\n{doc}")
    context = "\n\n---\n\n".join(labeled_context)

    detected_lang = detect_language(query)
    t_retrieved = time.perf_counter()

    raw_answer, llm_stats = call_llm(build_prompt(query, context, detected_lang))
    t_answered = time.perf_counter()

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

    timings = {
        "retrieval_s": t_retrieved - t_start,
        "llm_s": t_answered - t_retrieved,
        "total_s": time.perf_counter() - t_start,
        **llm_stats,
    }

    return {
        "answer": answer_clean,
        "sources": used_sources if used_sources else ["No specific source cited"],
        "detected_language": detected_lang,
        "all_retrieved_sources": all_sources,
        "timings": timings
    }


def format_timings(t):
    """One-line timing summary, e.g. for printing after each answer."""
    return (
        f"{t['total_s']:.1f}s total | search {t['retrieval_s']:.1f}s | "
        f"LLM {t['llm_s']:.1f}s (model load {t['load_s']:.1f}s, "
        f"read {t['prompt_tokens']} tokens in {t['prompt_s']:.1f}s, "
        f"wrote {t['output_tokens']} tokens in {t['output_s']:.1f}s)"
    )


if __name__ == "__main__":
    print(f"Total chunks in store: {collection.count()}")

    query = "What is the shipping weight based on the number of poles?"
    print(f"\nRunning 3 times to check consistency of clarification behavior:\n")
    for i in range(3):
        result = generate_answer(query)
        print(f"--- Run {i+1} ---")
        print(f"Answer: {result['answer']}")
        print(f"Sources: {result['sources']}\n")