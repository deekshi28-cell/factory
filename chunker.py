def chunk_text(text, chunk_size=800, overlap=100):
    """
    Splits plain paragraph text into overlapping chunks for embedding.
    Splits on paragraph/sentence boundaries where possible, not mid-word.
    Guarantees forward progress to avoid infinite loops on unusual text.
    """
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        if end < text_len:
            break_point = text.rfind("\n\n", start, end)
            if break_point == -1:
                break_point = text.rfind(". ", start, end)
            if break_point == -1:
                break_point = text.rfind(" ", start, end)
            if break_point != -1 and break_point > start:
                end = break_point + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # guarantee forward progress no matter what
        next_start = end - overlap
        if next_start <= start:
            next_start = end  # force forward movement if overlap would stall us
        start = next_start

        if start >= text_len:
            break

    return chunks


def chunk_table(rows, max_rows_per_chunk=15):
    """
    Splits a table (list of rows, first row = header) into chunks.
    Every chunk includes the header row, so no chunk ever loses column meaning.
    A single row is NEVER split across chunks.
    """
    if not rows:
        return []

    header = rows[0]
    data_rows = rows[1:]

    if len(data_rows) <= max_rows_per_chunk:
        return [{"header": header, "rows": data_rows}]

    chunks = []
    for i in range(0, len(data_rows), max_rows_per_chunk):
        chunk_rows = data_rows[i:i + max_rows_per_chunk]
        chunks.append({"header": header, "rows": chunk_rows})

    return chunks


if __name__ == "__main__":
    # --- Test 1: text chunking ---
    print("=== Test 1: chunk_text ===")
    sample_text = "This is a sentence. " * 100  # simulate a long paragraph
    result = chunk_text(sample_text, chunk_size=200, overlap=30)
    print(f"Chunks created: {len(result)}")
    print(f"First chunk length: {len(result[0])} chars")
    print(f"First chunk preview: {result[0][:100]}")

    # --- Test 2: table chunking ---
    print("\n=== Test 2: chunk_table ===")
    sample_table = [["Code", "Fault Description", "Action"]]  # header
    for i in range(40):  # simulate 40 data rows
        sample_table.append([f"E{i:03}", f"Fault type {i}", f"Action step {i}"])

    table_chunks = chunk_table(sample_table, max_rows_per_chunk=15)
    print(f"Table chunks created: {len(table_chunks)}")
    for i, tc in enumerate(table_chunks):
        print(f"  Chunk {i}: header={tc['header']}, rows={len(tc['rows'])}")