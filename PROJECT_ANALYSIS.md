# Factory Knowledge Assistant — Project Analysis

> A review of the whole `factory` repository: what the system does, how it is built, what has been done so far, open issues, and a roadmap for the next phases.
>
> *Analysis date: 2026-09-24. It is based on the repository at commit `f4f81c9` ("Add files via upload").*

---

## 1. Overview

**Factory Knowledge Assistant** is a **local, offline Retrieval-Augmented Generation (RAG) system**. It answers maintenance and engineering questions from a set of industrial equipment manuals: circuit breakers, relays, transformers, motor starters, VFDs, hoists, presses and similar equipment.

Key properties:

| Property | Details |
|---|---|
| Input formats | PDF (text-based **and** scanned), Word `.docx`, Excel `.xlsx`, plus embedded images |
| Languages | Answers in **English or Japanese**, whichever the question is written in |
| Runs fully locally | Embeddings via `sentence-transformers`; LLM and vision model served by **Ollama** on `localhost:11434` |
| Grounded answers | Answers use only retrieved context and cite the file plus page, table, section or row |
| Safety behaviour | Asks for clarification when a question is ambiguous or underspecified, or when tables conflict; told not to over-interpret safety statements |

The current interface is a **command-line chat** (`chat.py`). There is no web UI yet.

---

## 2. Architecture

```
                         ┌────────────────────────────── INGESTION ──────────────────────────────┐
                         │                                                                        │
 D:\FactoryKA\documents  │   readers.py                     chunker.py              search.py      │
 ┌──────────────────┐    │  ┌──────────────────────┐      ┌──────────────┐      ┌──────────────┐  │
 │ *.pdf (text)     │───▶│  │ read_pdf (PyMuPDF)   │─────▶│ chunk_text   │─────▶│ embed_text   │  │
 │ *.pdf (scanned)  │───▶│  │ read_pdf_with_ocr    │      │ 800c / 100   │      │ (BGE-M3)     │  │
 │ *.docx           │───▶│  │ read_docx (+merged   │─────▶│ chunk_table  │─────▶│ add_chunk    │──┼──┐
 │ *.xlsx           │───▶│  │   cell handling)     │      │ 15 rows+hdr  │      └──────────────┘  │  │
 └──────────────────┘    │  │ read_xlsx            │      └──────────────┘                        │  │
          │              │  └──────────────────────┘                                              │  │
          │              │  extract_images_from_{pdf,docx,xlsx}                                   │  │
          └─────────────▶│      │                                                                 │  │
                         │      ▼                                                                 │  │
                         │  batch_caption.py ──▶ Ollama qwen2.5vl:7b ──▶ all_captions.json         │  │
                         │                                                  │                      │  │
                         │                                  ingest_captions.py (picture_caption)───┼──┤
                         └────────────────────────────────────────────────────────────────────────┘  │
                                                                                                     ▼
                                                                      ChromaDB  D:\FactoryKA\chroma_db
                                                                      collection "factory_docs"
                                                                                                     │
                         ┌─────────────────────────────── QUERY ──────────────────────────────────┐  │
 user question ─────────▶│ chat.py → search.generate_answer()                                      │  │
                         │   1. detect_language (langdetect → Japanese / English)                   │  │
                         │   2. search_chunks  (top-5 by vector similarity)  ◀──────────────────────┼──┘
                         │   3. build prompt with [SOURCE n: file (page/table/row)] labels          │
                         │   4. Ollama qwen2.5:7b-instruct-q4_K_M                                    │
                         │   5. parse "USED SOURCES:" line → map to citations                       │
                         │   6. strip leaked "SOURCE n" mentions                                    │
                         └──────────────────────────────▶ { answer, sources, detected_language }  ──┘
```

### Chunk metadata schema

| `chunk_type` | Produced by | `page_number` field holds | Chunk ID pattern |
|---|---|---|---|
| `text` (PDF) | `ingest_pdf` | integer page number | `{file}_p{page}_c{i}` |
| `text` (DOCX) | `ingest_docx` | `"Section {i+1}"` | `{file}_para_c{i}` |
| `table` (DOCX) | `ingest_docx` | `"Table N"` / `"Table N, part M"` (+ `table_index`) | `{file}_table{t}_c{c}` |
| `table` (XLSX) | `ingest_xlsx` | `"Row A-B"` | `{file}_{sheet}_c{c}` |
| `picture_caption` | `ingest_captions.py` | page number (0 for DOCX/XLSX) (+ `image_path`) | `img_{file}_{imagename}` |

---

## 3. Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| PDF parsing and rendering | `pymupdf` (fitz) |
| OCR | `pytesseract` + Tesseract, language pack `jpn+eng`, pages rendered at 300 DPI |
| Word / Excel | `python-docx` (raw XML for `gridSpan`/`vMerge`), `openpyxl` |
| Images | `Pillow` |
| Embeddings | `sentence-transformers` → **`BAAI/bge-m3`** (multilingual) |
| Vector DB | **ChromaDB** `PersistentClient` |
| LLM (answers) | **Ollama** → `qwen2.5:7b-instruct-q4_K_M` |
| VLM (image captions) | **Ollama** → `qwen2.5vl:7b-q4_K_M` (`num_ctx` 8192) |
| Language detection | `langdetect` (seeded for deterministic output) |
| Listed but not yet used | `streamlit`, `pytest`, `pandas`, `scikit-learn` |

---

## 4. Repository map

### 4.1 Core pipeline

| File | Purpose |
|---|---|
| `readers.py` | Document readers: `read_pdf`, `read_pdf_with_ocr` (OCR runs on a page with < 20 chars of text), `read_docx` + `_read_table_grid` (merged-cell handling), `read_xlsx`, and `extract_images_from_pdf/docx/xlsx` with size filters |
| `chunker.py` | `chunk_text` (800 chars, 100 overlap, breaks at paragraph → sentence → word, always moves forward) and `chunk_table` (15 rows per chunk, header repeated, rows never split) |
| `search.py` | Embedding model and ChromaDB setup, `add_chunk`, `search_chunks`, `format_source`, `detect_language`, and the full RAG pipeline `generate_answer` with prompt rules and output parsing |
| `ingest.py` | `ingest_pdf`, `ingest_docx`, `ingest_xlsx`, `ingest_document` (routes by file type). `__main__` ingests the first 10 text PDFs |
| `add_documents.py` | Ingests 21 more PDFs (15 scanned with OCR, 6 text) |
| `chat.py` | Interactive command-line Q&A ("Phase 1 Q&A") |
| `test_caption.py` | `caption_image()` sends one image to the Ollama vision model |
| `batch_caption.py` | Extracts all images from every document and captions them, saving progress so it can resume, into `all_captions.json` |
| `ingest_captions.py` | Loads the captions into ChromaDB as `picture_caption` chunks |

### 4.2 Evaluation

| File | Purpose |
|---|---|
| `Phase2_Test_Questions.xlsx` | The main test set (question, expected answer, source, status) plus a progress summary sheet |
| `export_questions.py` | Converts the Excel test set to `test_questions.json` |
| `test_questions.json` | 99 test questions (id, category, question, expected_answer, expected_source) |
| `run_tests.py` | Runs every question through `generate_answer`, checks whether the expected source is cited, and writes `automatic_test_results.json` |
| `complete.py` | Checks whether a test run covered all 100 questions |
| `verify_source.py` | Shows the system's answer next to the raw source chunks for manual checking of accuracy and safety claims |

### 4.3 Diagnostics and one-off scripts

| File | Purpose |
|---|---|
| `debug.py` | Interactive Q&A that also prints the top-5 chunks it retrieved |
| `check_docs.py` | Lists page count and text/scanned status for each file in the corpus |
| `check_missing.py` | Lists files in the documents folder that are not yet in ChromaDB |
| `verify_corpus.py` | Total chunks and the list of ingested documents |
| `peek_chunks.py`, `peek_ocr.py`, `peek_pic.py` | Print sample text, OCR and caption chunks for chosen docs |
| `verify22.py` | Dumps the chunks of the 20-page maintenance manual `.docx` |
| `verifypic.py`, `verify_blade.py` | Prove that some facts (e.g. "1900 W", "ST-72-4X") exist **only** in picture captions of `2.pdf` |
| `check_filtered.py`, `check_filtered_all.py`, `s.py` | Image-filter statistics (found / too small / too large / kept) |
| `check_captions.py`, `check_all_captions.py`, `check_caption_status.py` | Caption progress and failure reports |
| `test_images.py`, `test_new_extractors.py`, `render_page.py` | Tests of image extraction and page rendering (`render_page.py` produced `test4_page18_highres.png`) |
| `test_ocr_check.py` | Counts how many pages of `1.pdf` needed OCR |
| `table_audit.py` | Flags DOCX tables whose header row looks wrong (merged title, numeric, empty) |
| `inspect31.py`, `fix6.py`, `test_table_question.py` | Investigation of the "shipping weight by number of poles" bug (`6.docx` Table 31) |
| `vfd.py`, `debug_vfd.py` | Inspect the VFD fault-code workbooks and check retrieval for them |
| `fix_all_pages.py` | Deletes and re-ingests 7 DOCX/XLSX files after position tracking (Table/Row/Section) was added |
| `cleanup_test_data.py` | Removes the `test_1` / `test_2` placeholder chunks |

### 4.4 Data files

| File | Content |
|---|---|
| `Document_Tracker.xlsx` | Corpus inventory: 31 PDFs with page count, text/scanned, has tables / alarm tables / wiring / pictures, equipment type, and download link |
| `all_captions.json` | **648** image captions from **26** source documents (0 failed) |
| `captions_7pdf.json` | Early pilot: 58 captions from `7.pdf` |
| `test4_page18_highres.png` | 300-DPI render of `7.pdf` page 18 (1.2 MB) |
| `requirements.txt` | Pinned dependencies (117 packages) |
| `output.txt` | Empty |

---

## 5. Corpus statistics (from `Document_Tracker.xlsx`)

| Metric | Value | Phase 0 target |
|---|---|---|
| PDF documents | **31** | 30+ ✅ |
| Total PDF pages | **755** | 500+ ✅ |
| Scanned PDFs (need OCR) | 16 | mix ✅ |
| Text-based PDFs | 15 | mix ✅ |
| Docs with alarm/fault tables | 19 | — |
| Largest document | `5.pdf`: 208 pages (Power/Insulated Case Circuit Breakers) | — |

The corpus also includes these Word/Excel files, which are referenced in the code but not listed in the tracker: `6.docx`, `Factory_Maintenance_Equipment_Master_Manual_20_Pages.docx`, `Mock_Maintenance_SOP_VFD_Process_Pump.docx`, `excel.xlsx`, `Factory_Assistance_Data_100_Rows.xlsx`, `VFD3000_Fault_Alarm_Codes.xlsx` and `VFD_Fault_Alarm_Code_Table.xlsx`.

Equipment covered includes network and dry-type transformers, directional ground relays, pneumatic timing relays, Class 8198 HV motor starters, Class 8965 hoist contactors, I-LINE panelboards, reduced-voltage and synchronous motor starters, drum controllers, a Siemens 7VE51 synchronising unit, a CNC UC100 motion controller, hydraulic presses, a circular saw, a 3Com LAN switch and VFD fault codes.

> The source documents, the ChromaDB database and the extracted images live **outside** the repo in `D:\FactoryKA\`. They are not version-controlled.

---

## 6. How to run (current state, Windows)

```bash
# prerequisites: Python 3, Tesseract (with jpn + eng language data), Ollama
pip install -r requirements.txt
pip install langdetect                       # used by search.py but missing from requirements.txt
ollama pull qwen2.5:7b-instruct-q4_K_M
ollama pull qwen2.5vl:7b-q4_K_M

# documents must be in D:\FactoryKA\documents (the path is hard-coded)
python ingest.py            # first 10 text PDFs
python add_documents.py     # 21 more PDFs (OCR for scanned ones)
python fix_all_pages.py     # DOCX / XLSX files
python batch_caption.py     # extract and caption images → all_captions.json  (slow)
python ingest_captions.py   # add captions to the vector DB

python chat.py              # ask questions
python debug.py             # ask questions and see the retrieved chunks
python run_tests.py         # automatic source-match test run
```

### Response-time target: under 15 seconds per question

`chat.py` loads the LLM before the first question and prints a timing line after each answer, e.g.
`[OK] 9.8s total | search 0.3s | LLM 9.5s (model load 0.0s, read 2100 tokens in 3.1s, wrote 120 tokens in 6.2s)`.
Run `python benchmark_latency.py --limit 20` to measure the median, 95th percentile and share of questions under 15 s on your machine.

Speed settings (environment variables; defaults in brackets):

| Variable | Default | Effect |
|---|---|---|
| `FACTORY_LLM_MODEL` | `qwen2.5:7b-instruct-q4_K_M` | Answer model. A smaller model (e.g. `qwen2.5:3b-instruct-q4_K_M`) is much faster on CPU; check quality with `run_tests.py` |
| `FACTORY_LLM_KEEP_ALIVE` | `60m` | How long Ollama keeps the model loaded between questions |
| `FACTORY_LLM_MAX_TOKENS` | `400` | Upper limit on answer length |
| `FACTORY_LLM_NUM_CTX` | `4096` | Context size (fits 5 chunks + instructions) |
| `FACTORY_N_RESULTS` | `5` | Chunks sent to the model; fewer = faster prompt reading |
| `FACTORY_CHROMA_DIR`, `FACTORY_OLLAMA_URL` | `D:\FactoryKA\chroma_db`, `http://localhost:11434` | Paths / server |

---

## 7. Changes made so far

The git history has only an initial commit and one bulk upload, so this timeline is reconstructed from the code, comments, script names and tracker sheets.

### Phase 0: corpus collection ✅
- Collected 31 public equipment manuals (755 pages, a 16/15 split of scanned and text PDFs) plus mock DOCX/XLSX maintenance files.
- Built `Document_Tracker.xlsx` to classify each document (tables, alarm tables, wiring diagrams, pictures, equipment type).
- Wrote `check_docs.py` to find scanned and text PDFs automatically.

### Phase 1: basic text RAG ✅
- PDF, DOCX and XLSX readers, and paragraph and table chunking (the table header is repeated in every table chunk).
- BGE-M3 embeddings, a ChromaDB store and Qwen2.5-7B answers via Ollama.
- The `chat.py` command-line interface.

### Phase 2: quality, coverage and evaluation ✅ (mostly)
| Change | Why / evidence |
|---|---|
| **OCR fallback for scanned PDFs** (`read_pdf_with_ocr`, `jpn+eng`, 300 DPI) | 16 of 31 PDFs are scanned; `add_documents.py` sets `use_ocr=True` for 15 of them, and `peek_ocr.py` / `test_ocr_check.py` check the result |
| **Merged-cell table fix** (`_read_table_grid`) | Wrong answers to "shipping weight based on number of poles" from `6.docx` Table 31: merged dimension cells were being copied into the weight column. Found via `inspect31.py`, `fix6.py` and `table_audit.py` |
| **Precise citations**: Table N / part M, Row A-B, Section N | Added to the DOCX and XLSX ingesters; `fix_all_pages.py` deletes and re-ingests the 7 affected files |
| **Image extraction and captioning** | Size filters (PDF 250–1800 px in the extractor default, 150 px min used in the batch, DOCX/XLSX 150 px min) skip icons and full-page scans. 648 images captioned by Qwen2.5-VL and ingested as `picture_caption` chunks |
| **Evidence for the caption pipeline** | `verifypic.py` / `verify_blade.py` show that facts such as "1900 W / 185 mm" and the blade model "ST-72-4X" can only be found through captions |
| **Prompt hardening** | Answer only from context; three kinds of clarification (ambiguous term, underspecified question, conflicting product tables); no over-interpretation of safety claims; cite only the sources actually used via a `USED SOURCES:` line |
| **Removal of "SOURCE N" leaks** | `_strip_source_mentions` catches any the model still writes |
| **Japanese support** | `langdetect` picks the answer language; a strict all-Japanese instruction with katakana term guidance. Test notes still mention "minor code-switching" |
| **Test set of 100 questions** | `Phase2_Test_Questions.xlsx` → `test_questions.json`, run by `run_tests.py` |

---

## 8. Evaluation status

From the summary sheet of `Phase2_Test_Questions.xlsx`:

| Category | Target | Written | Tested (Pass) |
|---|---|---|---|
| Table | 30 | 29 | 29 |
| Picture | 16 | 16 | 16 |
| Not Found | 20 | 21 | 21 |
| OCR/Scanned | 4 | 4 | 4 |
| General | 30 | 29 | 28 |
| **Total** | **100** | **99** | **98** |

Notes:
- The "pass" results were **judged by hand**. `run_tests.py` only checks the **source** automatically: whether the first expected source file appears in the cited sources. It does not check the answer text.
- The OCR category has only 4 questions, even though half the corpus is scanned.
- One question is still unwritten in each of the Table and General categories. The labels "Not found" and "Not Found" are used inconsistently in the JSON.

---

## 9. Known issues and technical debt

### Portability and configuration
1. **Hard-coded Windows paths** (`D:\FactoryKA\...`) in nearly every script, including the ChromaDB path in `search.py`.
2. `ingest_captions.py` builds chunk IDs by splitting on a backslash (`split(chr(92))`), so it breaks on Linux and macOS.
3. Model names and the Ollama URL are hard-coded in `search.py` and `test_caption.py`.
4. `langdetect` is imported but **missing from `requirements.txt`**.

### Correctness
5. A bare `except Exception: pass` around every `add_chunk` hides *all* errors (embedding failures, bad metadata), not just duplicate IDs. Recent ChromaDB versions may not raise on a duplicate `add` at all, so the "chunks added" counts can be inflated and a re-ingest can leave stale content in place.
6. The DOCX `"Section N"` label is really the **chunk index** over all paragraphs joined together, not a real section or heading.
7. XLSX `Row A-B` labels drift: `read_xlsx` drops empty rows, but the row counter assumes rows are contiguous.
8. Captions from DOCX and XLSX images get `page_number = 0`, so their citations show "page 0".
9. `ingest_pdf` does not record `used_ocr` in the metadata, so OCR chunks can't be told apart from text chunks.
10. `generate_answer` has no timeout or error handling on the Ollama HTTP call. `int(x)` parsing of `USED SOURCES` is fragile.
11. Language detection only recognises Japanese; everything else becomes English.

### Performance and design
12. `import search` **loads BGE-M3 and opens the database as a side effect**, so every diagnostic script pays the model-load cost.
13. Chunks are embedded and added one at a time; there is no batching.
14. Retrieval is vector-only and returns top-5, with no keyword search, reranking or metadata filters. Exact codes like `E-07` or catalog numbers rely only on the embedding.
15. The PDF text chunk boundaries stop at the page break, so content that runs across two pages is split.

### Repository hygiene
16. About 25 one-off scripts sit next to the core modules, and several are copies of each other (`s.py`, `check_filtered.py`, `check_filtered_all.py`).
17. Generated data (a 1.2 MB PNG, a 374 KB caption JSON) is committed; there is no `.gitignore`.
18. There are no unit tests, even though `pytest` is installed. `readers.py` and `chunker.py` have `__main__` smoke tests only.
19. There is no real README, license or setup docs (this file is the first).
20. `check_caption_status.py` hard-codes the total of 648. `complete.py` hard-codes 100.

---

## 10. Roadmap: next phases

Priorities: 🔴 do first · 🟠 important · 🟢 nice to have

### Phase 3: clean up and harden the foundation
- [ ] 🔴 Add `config.py` plus `.env` (`DOCS_DIR`, `CHROMA_DIR`, `IMAGES_DIR`, `OLLAMA_URL`, `LLM_MODEL`, `VLM_MODEL`, `EMBED_MODEL`) and use `pathlib` everywhere
- [ ] 🔴 Add `langdetect` to `requirements.txt`; split runtime and dev dependencies
- [ ] 🔴 Replace `collection.add` with `upsert` and swap the silent excepts for logging and real counts
- [ ] 🔴 Fix `ingest_captions.py` path handling (`os.path.basename`)
- [ ] 🟠 Restructure the repo: `factory_ka/` package (readers, chunker, store, rag, captioning), `scripts/` (ingest, caption, eval), `scripts/diagnostics/` (the one-off tools), `data/` (ignored)
- [ ] 🟠 Load the embedding model and DB client lazily (`get_collection()`), and embed in batches
- [ ] 🟠 A single command to ingest everything (`python -m factory_ka.ingest --all`) driven by `Document_Tracker.xlsx` or a manifest, with automatic OCR detection instead of hand-kept lists
- [ ] 🟠 Fix the citation labels: real DOCX headings or sections, correct XLSX row numbers, the `used_ocr` flag, and DOCX/XLSX caption locations
- [ ] 🟢 `.gitignore` for generated data, images and the database; move large artefacts out of git

### Phase 4: retrieval and answer quality
- [ ] 🔴 **Hybrid search**: BM25 or keyword search plus vector search, fused with RRF. This is critical for fault codes (`E-12`), catalog numbers and model numbers
- [ ] 🟠 **Reranking** with a cross-encoder (e.g. `BAAI/bge-reranker-v2-m3`, which is multilingual): retrieve 20–30, keep the best 5
- [ ] 🟠 Metadata filters by document or equipment type, using the equipment category from the tracker
- [ ] 🟠 Chunks that can span page breaks, plus "parent page" context expansion
- [ ] 🟠 Better scanned-PDF pipeline: layout- and table-aware OCR (e.g. docling, PaddleOCR or OCR through the VLM for table pages), with OCR confidence stored in metadata
- [ ] 🟢 Link picture captions to the text on the same page; show images with the answers
- [ ] 🟢 Wider language support (Japanese, English and others), and fixes for the Japanese code-switching noted in the tests
- [ ] 🟢 Try larger or newer local LLMs and compare them on the test set

### Phase 5: evaluation framework
- [ ] 🔴 Grade answers automatically: number and keyword matching against `expected_answer`, plus an LLM-as-judge score (correct / partial / wrong / correctly declined)
- [ ] 🔴 Retrieval metrics: recall@k and MRR of the expected source and page, measured separately from generation
- [ ] 🟠 `run_tests.py`: resume support, timestamped result files, per-category summaries, and diffs against the last run to catch regressions
- [ ] 🟠 Finish the test set (100 or more), grow the OCR/Scanned category (4 → 15+), and add more Japanese questions
- [ ] 🟠 `pytest` unit tests for `chunk_text`, `chunk_table`, `_read_table_grid` (merged-cell fixtures), the source parsing and `_strip_source_mentions`
- [ ] 🟢 CI (GitHub Actions) that runs the unit tests and linting

### Phase 6: user interface and deployment
- [ ] 🟠 **Streamlit web app** (already in `requirements.txt`): chat, clickable citations, source snippets, image previews and a language toggle
- [ ] 🟠 Admin page: upload documents, ingest them, see corpus and caption status (replacing the `check_*` scripts)
- [ ] 🟠 Capture user feedback (👍/👎 plus a comment) for evaluation data
- [ ] 🟢 Docker Compose (app, Ollama and a persistent ChromaDB volume) for on-premise factory deployment
- [ ] 🟢 Optionally stream answer tokens

### Phase 7: production readiness
- [ ] 🟠 Incremental ingestion using file hashes: re-ingest only changed documents and remove chunks from deleted ones
- [ ] 🟠 Log queries and answers with retrieved chunk IDs, for auditing (important for safety-related answers)
- [ ] 🟢 Authentication and role-based access to documents
- [ ] 🟢 Monitoring of latency, "not found" rate and feedback score
- [ ] 🟢 Integration with CMMS or maintenance ticket systems (e.g. look up a fault code from a work order)

### Suggested order of work
1. **Phase 3**: config, dependencies, upsert and logging. This unblocks everything else and makes the project run outside Windows.
2. **Phase 5 (automatic grading)**: build the measuring tools before changing retrieval.
3. **Phase 4 (hybrid search and reranking)**: the biggest expected gain in accuracy, measured with the Phase 5 tools.
4. **Phase 6 (Streamlit UI)**: the first version end users can use.
5. **Phase 7**: hardening for real deployment.
