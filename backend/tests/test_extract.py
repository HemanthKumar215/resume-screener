import io
import zipfile

import pytest
from reportlab.pdfgen import canvas

from conftest import FakeTextract
from screener.extract import ExtractionError, extract_text


def _blank_pdf(pages=1) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for _ in range(pages):
        c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_and_docx(samples):
    text, method = extract_text((samples / "ananya_iyer.pdf").read_bytes(), "a.pdf")
    assert method == "pdf" and "Ananya Iyer" in text
    text, method = extract_text((samples / "arjun_reddy.docx").read_bytes(), "a.docx")
    assert method == "docx" and "Terraform" in text


def test_txt():
    assert extract_text(b"Hello resume", "cv.TXT") == ("Hello resume", "text")


def test_scanned_pdf_uses_textract():
    fake = FakeTextract()
    text, method = extract_text(_blank_pdf(), "scan.pdf", textract=fake)
    assert method == "textract" and "Python" in text and fake.calls == 1


def test_scanned_multipage_pdf_is_rejected():
    with pytest.raises(ExtractionError, match="multi-page"):
        extract_text(_blank_pdf(3), "scan.pdf", textract=FakeTextract())


def test_image_uses_textract():
    assert extract_text(b"\x89PNG fake", "photo.png", textract=FakeTextract())[1] == "textract"


@pytest.mark.parametrize(
    "data,name,msg",
    [
        (b"x", "resume.exe", "Unsupported"),
        (b"", "resume.pdf", "empty"),
        (b"not a pdf", "resume.pdf", "couldn't be read"),
        (b"not a zip", "resume.docx", "couldn't be read"),
    ],
)
def test_bad_files(data, name, msg):
    with pytest.raises(ExtractionError, match=msg):
        extract_text(data, name)


def test_ocr_unavailable_without_client():
    with pytest.raises(ExtractionError, match="OCR"):
        extract_text(b"img", "a.jpg")


def test_docx_without_document_xml():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("other.xml", "<x/>")
    with pytest.raises(ExtractionError):
        extract_text(buf.getvalue(), "a.docx")
