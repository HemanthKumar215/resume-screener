"""Turn an uploaded resume file into plain text.

- Digital PDFs: pypdf (free, fast, no AWS call).
- DOCX: read word/document.xml directly (no extra dependency).
- Images and scanned PDFs: Amazon Textract OCR.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MIN_TEXT_CHARS = 120  # below this, a PDF is probably scanned and needs OCR
MAX_PDF_PAGES = 10

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}


class ExtractionError(Exception):
    """A problem with the file itself (shown to the recruiter, not retried)."""


def extension(filename: str) -> str:
    m = re.search(r"\.[A-Za-z0-9]+$", filename or "")
    return m.group(0).lower() if m else ""


def extract_text(data: bytes, filename: str, textract=None) -> tuple[str, str]:
    """Return (text, method). `textract` is a boto3 Textract client, used only when OCR is needed."""
    ext = extension(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise ExtractionError(f"Unsupported file type {ext or '(none)'}. Upload PDF, DOCX, TXT, PNG or JPG.")
    if not data:
        raise ExtractionError("The file is empty.")

    if ext == ".txt":
        return data.decode("utf-8", errors="replace"), "text"
    if ext == ".docx":
        return _docx_text(data), "docx"
    if ext in (".png", ".jpg", ".jpeg"):
        return _ocr(data, textract), "textract"

    text, pages = _pdf_text(data)
    if len(text.strip()) >= MIN_TEXT_CHARS:
        return text, "pdf"
    if pages > 1:
        # Synchronous Textract only handles single-page PDFs; async jobs aren't worth it for a resume.
        raise ExtractionError("This looks like a scanned multi-page PDF. Upload a text-based PDF or an image instead.")
    return _ocr(data, textract), "textract"


def _pdf_text(data: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise ExtractionError("The PDF is password-protected.") from exc
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((p.extract_text() or "") for p in pages), len(reader.pages)
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError) as exc:
        raise ExtractionError("The PDF couldn't be read. It may be corrupted.") from exc


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ExtractionError("The DOCX file couldn't be read.") from exc
    root = ElementTree.fromstring(xml)
    lines = []
    for para in root.iter(f"{_W}p"):
        parts = []
        for node in para.iter():
            if node.tag == f"{_W}t" and node.text:
                parts.append(node.text)
            elif node.tag == f"{_W}tab":
                parts.append(" ")
        lines.append("".join(parts))
    return "\n".join(lines)


def _ocr(data: bytes, textract) -> str:
    if textract is None:
        raise ExtractionError("This file needs OCR, which isn't available in this environment.")
    if len(data) > 10 * 1024 * 1024:
        raise ExtractionError("Images must be under 10 MB.")
    try:
        resp = textract.detect_document_text(Document={"Bytes": data})
    except textract.exceptions.UnsupportedDocumentException as exc:
        raise ExtractionError("Textract couldn't read this document.") from exc
    except textract.exceptions.BadDocumentException as exc:
        raise ExtractionError("The document is damaged or in an unsupported format.") from exc
    lines = [b["Text"] for b in resp.get("Blocks", []) if b.get("BlockType") == "LINE" and b.get("Text")]
    text = "\n".join(lines)
    if not text.strip():
        raise ExtractionError("No text could be read from this file.")
    return text
