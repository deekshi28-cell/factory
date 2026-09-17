import pymupdf  # modern import; older code sometimes uses "import fitz"
import os
import pytesseract
from PIL import Image
import io
import docx
from docx.oxml.ns import qn
import openpyxl
import zipfile

# If Tesseract isn't on PATH for some reason, uncomment and set the path:
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def read_pdf(filepath):
    """
    Reads a PDF and returns a list of pages, each with page number and text.
    Works for text-based PDFs. Scanned PDFs will return empty/near-empty text.
    """
    doc = pymupdf.open(filepath)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        pages.append({
            "page_number": page_num + 1,
            "text": text,
            "source_file": os.path.basename(filepath)
        })
    doc.close()
    return pages


def read_pdf_with_ocr(filepath, ocr_lang="jpn+eng"):
    """
    Reads a PDF page by page. If a page has little/no extractable text,
    falls back to OCR on that page's rendered image.
    """
    doc = pymupdf.open(filepath)
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text()
        used_ocr = False

        if len(text.strip()) < 20:
            pix = page.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang=ocr_lang)
            used_ocr = True

        pages.append({
            "page_number": page_num + 1,
            "text": text,
            "source_file": os.path.basename(filepath),
            "used_ocr": used_ocr
        })
    doc.close()
    return pages


def _read_table_grid(table):
    """
    Reads a python-docx Table into a clean grid of rows, correctly handling
    merged cells:
    - gridSpan (horizontal merge): the merged value is placed only in the
      first spanned column; other spanned columns are left blank, instead
      of duplicating the same value across every column it touches.
    - vMerge (vertical merge): only the row where the merge starts ("restart")
      keeps the value; continuation rows are left blank, instead of the
      value getting silently dropped or a blank row appearing to be separate,
      unrelated data.

    Without this, merged cells get misread - e.g. a merged "dimension" cell
    spanning into the "weight" column gets duplicated into the weight column,
    making a dimension value look like a weight value.
    """
    num_cols = len(table.columns)
    grid = []
    for row in table.rows:
        grid_row = [None] * num_cols
        col_idx = 0
        tr = row._tr
        for tc in tr.findall(qn('w:tc')):
            tcPr = tc.find(qn('w:tcPr'))
            vmerge = None
            gridspan = 1
            if tcPr is not None:
                vm = tcPr.find(qn('w:vMerge'))
                gs = tcPr.find(qn('w:gridSpan'))
                if vm is not None:
                    vmerge = vm.get(qn('w:val'), 'continue')
                if gs is not None:
                    gridspan = int(gs.get(qn('w:val')))

            text = ''.join(t.text for t in tc.iter(qn('w:t'))).strip()

            while col_idx < num_cols and grid_row[col_idx] is not None:
                col_idx += 1

            if vmerge == 'continue':
                text = ''

            for i in range(gridspan):
                if col_idx + i < num_cols:
                    grid_row[col_idx + i] = text if i == 0 else ''
            col_idx += gridspan

        grid.append([c if c is not None else '' for c in grid_row])
    return grid


def read_docx(filepath):
    """
    Reads a Word document and returns paragraphs and tables separately.
    Tables are read with proper merged-cell handling (see _read_table_grid).
    """
    doc = docx.Document(filepath)

    paragraphs = []
    for para in doc.paragraphs:
        if para.text.strip():
            paragraphs.append(para.text)

    tables = []
    for table_idx, table in enumerate(doc.tables):
        rows = _read_table_grid(table)
        tables.append({
            "table_index": table_idx,
            "rows": rows
        })

    return {
        "source_file": os.path.basename(filepath),
        "paragraphs": paragraphs,
        "tables": tables
    }


def read_xlsx(filepath):
    """
    Reads an Excel workbook and returns all sheets with their cell data as rows.
    """
    wb = openpyxl.load_workbook(filepath, data_only=True)
    sheets = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                rows.append(list(row))
        sheets.append({
            "sheet_name": sheet_name,
            "rows": rows
        })
    return {
        "source_file": os.path.basename(filepath),
        "sheets": sheets
    }


def extract_images_from_pdf(filepath, output_folder, min_size=250, max_size=1800):
    """
    Extracts embedded images, skipping small fragments (icons/arrows)
    AND skipping full-page-sized images (which are just scanned pages, not real diagrams).
    """
    os.makedirs(output_folder, exist_ok=True)
    doc = pymupdf.open(filepath)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    images = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = doc.extract_image(xref)
            width = base_image["width"]
            height = base_image["height"]

            if width < min_size or height < min_size:
                continue
            if width > max_size or height > max_size:
                continue

            ext = base_image["ext"]
            img_filename = f"{base_name}_p{page_num+1}_img{img_index}.{ext}"
            img_path = os.path.join(output_folder, img_filename)

            with open(img_path, "wb") as f:
                f.write(base_image["image"])

            images.append({
                "image_path": img_path,
                "page_number": page_num + 1,
                "source_file": os.path.basename(filepath)
            })

    doc.close()
    return images


def extract_images_from_docx(filepath, output_folder, min_size=150):
    """
    Extracts embedded images from a Word (.docx) file, skipping tiny icons/fragments.
    """
    os.makedirs(output_folder, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    images = []
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            img_idx = 0
            for name in z.namelist():
                if 'media/' in name and not name.endswith('/'):
                    data = z.read(name)
                    try:
                        img = Image.open(io.BytesIO(data))
                        w, h = img.size
                        if w < min_size or h < min_size:
                            continue
                        ext = os.path.splitext(name)[1].lstrip('.').lower()
                        if not ext:
                            ext = "png"
                        img_filename = f"{base_name}_docx_img{img_idx}.{ext}"
                        img_path = os.path.join(output_folder, img_filename)
                        with open(img_path, "wb") as f:
                            f.write(data)
                        images.append({
                            "image_path": img_path,
                            "page_number": 0,
                            "source_file": os.path.basename(filepath)
                        })
                        img_idx += 1
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error extracting images from {filepath}: {e}")
    return images


def extract_images_from_xlsx(filepath, output_folder, min_size=150):
    """
    Extracts embedded images from an Excel (.xlsx) file, skipping tiny icons/fragments.
    """
    os.makedirs(output_folder, exist_ok=True)
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    images = []
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            img_idx = 0
            for name in z.namelist():
                if 'media/' in name and not name.endswith('/'):
                    data = z.read(name)
                    try:
                        img = Image.open(io.BytesIO(data))
                        w, h = img.size
                        if w < min_size or h < min_size:
                            continue
                        ext = os.path.splitext(name)[1].lstrip('.').lower()
                        if not ext:
                            ext = "png"
                        img_filename = f"{base_name}_xlsx_img{img_idx}.{ext}"
                        img_path = os.path.join(output_folder, img_filename)
                        with open(img_path, "wb") as f:
                            f.write(data)
                        images.append({
                            "image_path": img_path,
                            "page_number": 0,
                            "source_file": os.path.basename(filepath)
                        })
                        img_idx += 1
                    except Exception:
                        pass
    except Exception as e:
        print(f"Error extracting images from {filepath}: {e}")
    return images


if __name__ == "__main__":
    # Quick verification test: Table 30 and 31 of 6.docx, which previously
    # produced inconsistent/wrong shipping weight answers due to unhandled
    # merged cells.
    print("=== Verifying merged-cell fix on 6.docx ===")
    test_file = r"D:\FactoryKA\documents\6.docx"
    result = read_docx(test_file)

    for idx in [30, 31]:
        print(f"\n--- Table {idx} ---")
        for row in result["tables"][idx]["rows"]:
            print(row)