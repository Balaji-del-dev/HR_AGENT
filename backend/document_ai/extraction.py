"""Steps 4 and 5: text extraction with page data, OCR fallback, and sanitizing.

Hidden text is dropped while reading: white text, tiny fonts, text placed off
the page, and hidden DOCX runs. These are the usual ways to smuggle
instructions to a model inside a resume.
"""

import io
import logging
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import pymupdf

from document_ai.validation import DOCX, PDF, FileRejected

logger = logging.getLogger(__name__)

WHITE = 0xFFFFFF
MIN_FONT_SIZE = 4.0
OCR_MIN_CHARS = 20


@dataclass
class ExtractedDocument:
    pages: list[str]
    ocr_used: bool = False
    flags: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)


def clean_text(text: str) -> tuple[str, int]:
    """Normalize Unicode and strip invisible characters. Returns (text, removed count)."""
    text = unicodedata.normalize("NFKC", text)
    kept: list[str] = []
    removed = 0
    for char in text:
        category = unicodedata.category(char)
        if category == "Cf" or (category == "Cc" and char not in "\n\t"):
            removed += 1
            continue
        kept.append(" " if char == "\t" else char)
    return "".join(kept), removed


def _normalize_lines(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    out: list[str] = []
    for line in lines:
        if line or (out and out[-1]):
            out.append(line)
    return "\n".join(out).strip()


def extract_pdf(data: bytes, *, max_pages: int, ocr: bool = True) -> ExtractedDocument:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")  # type: ignore[no-untyped-call]
    except (RuntimeError, ValueError) as exc:
        raise FileRejected("The PDF could not be opened.") from exc
    with document:
        if document.needs_pass:
            raise FileRejected("Password-protected PDFs are not accepted.")
        if document.page_count > max_pages:
            raise FileRejected(f"The resume has {document.page_count} pages; the limit is {max_pages}.")
        result = ExtractedDocument(pages=[])
        hidden = 0
        for page_number in range(document.page_count):
            page = document[page_number]
            rect = page.rect
            lines: list[str] = []
            for block in page.get_text("dict")["blocks"]:  # type: ignore[no-untyped-call]
                for line in block.get("lines", []):
                    parts: list[str] = []
                    for span in line.get("spans", []):
                        x0, y0, x1, y1 = span["bbox"]
                        off_page = x1 < rect.x0 or x0 > rect.x1 or y1 < rect.y0 or y0 > rect.y1
                        if span.get("color") == WHITE or span.get("size", 12) < MIN_FONT_SIZE or off_page:
                            if span["text"].strip():
                                hidden += 1
                            continue
                        parts.append(span["text"])
                    if parts:
                        lines.append("".join(parts))
            text = "\n".join(lines)
            if ocr and len(text.strip()) < OCR_MIN_CHARS:
                ocr_text = _ocr_page(page)
                if ocr_text.strip():
                    text = ocr_text
                    result.ocr_used = True
            cleaned, removed = clean_text(text)
            if removed:
                result.flags.append(f"page {page.number + 1}: removed {removed} invisible characters")
            result.pages.append(_normalize_lines(cleaned))
        if hidden:
            result.flags.append(f"dropped {hidden} hidden text spans (white, tiny or off-page)")
    return result


def _ocr_page(page: pymupdf.Page) -> str:
    try:
        import pytesseract
        from PIL import Image

        pixmap = page.get_pixmap(dpi=200)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))  # type: ignore[no-untyped-call]
        return str(pytesseract.image_to_string(image))
    except Exception:
        logger.warning("OCR failed", exc_info=True)
        return ""


def extract_docx(data: bytes) -> ExtractedDocument:
    import docx
    from docx.shared import Pt, RGBColor

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise FileRejected("The DOCX could not be opened.") from exc
    hidden = 0
    lines: list[str] = []

    def visible_text(paragraph: Any) -> str:
        nonlocal hidden
        parts = []
        for run in paragraph.runs:
            font = run.font
            is_white = (
                font.color is not None and font.color.type is not None and font.color.rgb == RGBColor(0xFF, 0xFF, 0xFF)
            )
            tiny = font.size is not None and font.size < Pt(MIN_FONT_SIZE)
            if font.hidden or is_white or tiny:
                if run.text.strip():
                    hidden += 1
                continue
            parts.append(run.text)
        return "".join(parts)

    for paragraph in document.paragraphs:
        lines.append(visible_text(paragraph))
    for table in document.tables:
        for row in table.rows:
            cells = [" ".join(visible_text(p) for p in cell.paragraphs) for cell in row.cells]
            lines.append(" | ".join(cell for cell in cells if cell.strip()))
    cleaned, removed = clean_text("\n".join(lines))
    result = ExtractedDocument(pages=[_normalize_lines(cleaned)])
    if removed:
        result.flags.append(f"removed {removed} invisible characters")
    if hidden:
        result.flags.append(f"dropped {hidden} hidden text runs (hidden, white or tiny)")
    return result


def extract(data: bytes, content_type: str, *, max_pages: int) -> ExtractedDocument:
    if content_type == PDF:
        return extract_pdf(data, max_pages=max_pages)
    if content_type == DOCX:
        return extract_docx(data)
    raise FileRejected(f"Unsupported type {content_type}.")
