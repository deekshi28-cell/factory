# factory — Factory Knowledge Assistant

A local, offline RAG (Retrieval-Augmented Generation) assistant that answers questions from industrial equipment manuals (PDF, including scanned pages, plus DOCX and XLSX). It answers in English or Japanese and cites its sources.

- **Embeddings:** BAAI/bge-m3 · **Vector DB:** ChromaDB · **LLM:** Qwen2.5-7B (Ollama) · **Image captions:** Qwen2.5-VL-7B (Ollama) · **OCR:** Tesseract (jpn+eng)
- **Entry points:** `ingest.py` / `add_documents.py` (ingest), `batch_caption.py` + `ingest_captions.py` (images), `chat.py` (Q&A), `run_tests.py` (evaluation)

See **[PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md)** for the full architecture, repository map, change history, known issues and next-phase roadmap.
