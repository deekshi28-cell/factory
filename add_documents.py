import os
from ingest import ingest_pdf, ingest_docx, ingest_xlsx

new_files = [
    # scanned PDFs - need OCR
    {"path": r"D:\FactoryKA\documents\1.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\10.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\15.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\2.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\3.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\4 .pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\8198.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\ACT.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\Circuit breaker.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\ci.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\drum.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\e.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\h.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\seimens.pdf", "type": "pdf", "use_ocr": True},
    {"path": r"D:\FactoryKA\documents\typeki.odf.pdf", "type": "pdf", "use_ocr": True},

    # text-based PDFs - no OCR needed
    {"path": r"D:\FactoryKA\documents\6.pdf", "type": "pdf", "use_ocr": False},
    {"path": r"D:\FactoryKA\documents\c.pdf", "type": "pdf", "use_ocr": False},
    {"path": r"D:\FactoryKA\documents\dgr.pdf", "type": "pdf", "use_ocr": False},
    {"path": r"D:\FactoryKA\documents\hoist.pdf", "type": "pdf", "use_ocr": False},
    {"path": r"D:\FactoryKA\documents\i-line.pdf", "type": "pdf", "use_ocr": False},
    {"path": r"D:\FactoryKA\documents\synchronous.pdf", "type": "pdf", "use_ocr": False},
]

for f in new_files:
    if not os.path.exists(f["path"]):
        print(f"NOT FOUND, skipping: {f['path']}")
        continue

    print(f"Ingesting {os.path.basename(f['path'])}...")
    if f["type"] == "pdf":
        count = ingest_pdf(f["path"], use_ocr=f.get("use_ocr", False))
    elif f["type"] == "docx":
        count = ingest_docx(f["path"])
    elif f["type"] == "xlsx":
        count = ingest_xlsx(f["path"])
    else:
        print(f"  Unknown type: {f['type']}")
        continue

    print(f"  -> {count} chunks added")