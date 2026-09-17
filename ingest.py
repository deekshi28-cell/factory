import os
from readers import read_pdf, read_pdf_with_ocr, read_docx, read_xlsx
from chunker import chunk_text, chunk_table
from search import add_chunk, generate_answer

def ingest_pdf(filepath, use_ocr=False):
    reader_fn = read_pdf_with_ocr if use_ocr else read_pdf
    pages = reader_fn(filepath)
    count = 0
    for page in pages:
        chunks = chunk_text(page["text"])
        for i, chunk_content in enumerate(chunks):
            chunk_id = f"{page['source_file']}_p{page['page_number']}_c{i}"
            try:
                add_chunk(
                    chunk_id=chunk_id,
                    text=chunk_content,
                    metadata={
                        "source_file": page["source_file"],
                        "page_number": page["page_number"],
                        "chunk_type": "text"
                    }
                )
                count += 1
            except Exception:
                pass  # skip if already exists (duplicate ID)
    return count


def ingest_docx(filepath):
    result = read_docx(filepath)
    source = result["source_file"]
    count = 0

    # ingest paragraphs as text chunks - track paragraph number as position reference
    full_text = "\n\n".join(result["paragraphs"])
    chunks = chunk_text(full_text)
    for i, chunk_content in enumerate(chunks):
        chunk_id = f"{source}_para_c{i}"
        try:
            add_chunk(
                chunk_id=chunk_id,
                text=chunk_content,
                metadata={"source_file": source, "page_number": f"Section {i+1}", "chunk_type": "text"}
            )
            count += 1
        except Exception:
            pass

    # ingest tables as table chunks - track actual table number
    for t_idx, table in enumerate(result["tables"]):
        rows = table["rows"]
        if not rows:
            continue
        table_chunks = chunk_table(rows, max_rows_per_chunk=15)
        for c_idx, tc in enumerate(table_chunks):
            header_str = " | ".join(str(h) for h in tc["header"])
            rows_str = "\n".join(" | ".join(str(cell) for cell in row) for row in tc["rows"])
            table_text = f"Table columns: {header_str}\n{rows_str}"

            page_label = f"Table {t_idx + 1}" if len(table_chunks) == 1 else f"Table {t_idx + 1}, part {c_idx + 1}"

            chunk_id = f"{source}_table{t_idx}_c{c_idx}"
            try:
                add_chunk(
                    chunk_id=chunk_id,
                    text=table_text,
                    metadata={"source_file": source, "page_number": page_label, "chunk_type": "table", "table_index": t_idx}
                )
                count += 1
            except Exception:
                pass

    return count


def ingest_xlsx(filepath):
    result = read_xlsx(filepath)
    source = result["source_file"]
    count = 0

    for sheet in result["sheets"]:
        rows = sheet["rows"]
        if not rows:
            continue
        table_chunks = chunk_table(rows, max_rows_per_chunk=15)
        row_tracker = 2  # header is row 1, data starts row 2
        for c_idx, tc in enumerate(table_chunks):
            header_str = " | ".join(str(h) for h in tc["header"])
            rows_str = "\n".join(" | ".join(str(cell) for cell in row) for row in tc["rows"])
            table_text = f"Sheet: {sheet['sheet_name']}\nColumns: {header_str}\n{rows_str}"

            start_row = row_tracker
            end_row = row_tracker + len(tc["rows"]) - 1
            row_tracker = end_row + 1

            chunk_id = f"{source}_{sheet['sheet_name']}_c{c_idx}"
            try:
                add_chunk(
                    chunk_id=chunk_id,
                    text=table_text,
                    metadata={"source_file": source, "page_number": f"Row {start_row}-{end_row}", "chunk_type": "table"}
                )
                count += 1
            except Exception:
                pass

    return count


def ingest_document(filepath, use_ocr=False):
    """Routes to the right ingester based on file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return ingest_pdf(filepath, use_ocr=use_ocr)
    elif ext == ".docx":
        return ingest_docx(filepath)
    elif ext == ".xlsx":
        return ingest_xlsx(filepath)
    else:
        print(f"  Skipped (unsupported type): {filepath}")
        return 0


if __name__ == "__main__":
    documents_folder = r"D:\FactoryKA\documents"

    # pick 10 documents - mix of text and scanned PDFs, plus your word/excel files
    # UPDATE these filenames to match ones you actually want to test with
    files_to_ingest = [
        "11.pdf", "12.pdf", "13.pdf", "14.pdf", "17.pdf",
        "5.pdf", "7.pdf", "8.pdf", "9.pdf", "reduced vol.pdf"
    ]

    total = 0
    for fname in files_to_ingest:
        filepath = os.path.join(documents_folder, fname)
        if not os.path.exists(filepath):
            print(f"  Not found, skipping: {fname}")
            continue
        print(f"Ingesting {fname}...")
        n = ingest_document(filepath)
        print(f"  -> {n} chunks added")
        total += n

    print(f"\nTotal chunks ingested: {total}")