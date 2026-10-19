"""PDF validation and page-preserving Markdown extraction."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from config import MAX_PAGES


class PDFValidationError(ValueError):
    """Raised when an upload is not a supported, readable PDF."""


def validate_pdf(data: bytes, filename: str) -> dict[str, Any]:
    if not filename.lower().endswith(".pdf"):
        raise PDFValidationError("Chỉ nhận file có đuôi .pdf.")
    if b"%PDF-" not in data[:1024]:
        raise PDFValidationError("Nội dung file không có chữ ký PDF hợp lệ.")

    import pymupdf

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PDFValidationError(f"Không mở được PDF: {exc}") from exc

    try:
        if document.needs_pass:
            raise PDFValidationError("PDF được mã hóa hoặc yêu cầu mật khẩu.")
        page_count = document.page_count
        if page_count < 1:
            raise PDFValidationError("PDF không có trang nào.")
        if page_count > MAX_PAGES:
            raise PDFValidationError(
                f"PDF có {page_count} trang; giới hạn MVP hiện tại là {MAX_PAGES} trang."
            )
        metadata = document.metadata or {}
        return {
            "page_count": page_count,
            "title": metadata.get("title") or "",
            "author": metadata.get("author") or "",
        }
    finally:
        document.close()


def parse_pdf(pdf_path: Path, expected_page_count: int) -> tuple[list[dict[str, Any]], str]:
    """Return page records with 1-based page numbers and combined Markdown."""
    import pymupdf4llm

    parsed = pymupdf4llm.to_markdown(
        str(pdf_path), page_chunks=True, show_progress=False
    )
    if not isinstance(parsed, list):
        raise RuntimeError("PyMuPDF4LLM không trả về các trang riêng biệt.")

    pages: list[dict[str, Any]] = []
    for index, item in enumerate(parsed):
        if isinstance(item, dict):
            text = str(item.get("text") or "")
            raw_metadata = item.get("metadata") or {}
            title = raw_metadata.get("title") or ""
        else:
            text = str(item or "")
            title = ""
        page_number = index + 1
        warnings = _page_warnings(text)
        if not text.strip():
            warnings.append(
                "Không trích xuất được văn bản; trang có thể là ảnh scan hoặc rỗng."
            )
        pages.append(
            {
                "page_number": page_number,
                "title": title,
                "markdown": text,
                "parser_warning": warnings,
            }
        )

    if len(pages) != expected_page_count:
        raise RuntimeError(
            "Số trang PyMuPDF4LLM trả về không khớp PDF "
            f"({len(pages)} so với {expected_page_count})."
        )

    parsed_markdown = "\n\n".join(
        f"<!-- Page {page['page_number']} -->\n\n{page['markdown']}" for page in pages
    )
    return pages, parsed_markdown


def render_page_png(pdf_path: Path, page_number: int) -> bytes:
    """Render one 1-based source PDF page for code/math spot checks."""
    import pymupdf

    document = pymupdf.open(pdf_path)
    try:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("Page number is outside the PDF.")
        page = document.load_page(page_number - 1)
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        return pixmap.tobytes("png")
    finally:
        document.close()


def _page_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    if "\ufffd" in text or "\u25a1" in text:
        warnings.append("Có ký tự thay thế/ô vuông; cần đối chiếu trang PDF gốc.")
    if text.count("```") % 2:
        warnings.append("Khối code có dấu fence không cân bằng; cấu trúc code có thể sai.")

    opened = len(re.findall(r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?)\}", text))
    closed = len(re.findall(r"\\end\{(equation\*?|align\*?|gather\*?|multline\*?)\}", text))
    if opened != closed:
        warnings.append("Môi trường công thức LaTeX không cân bằng; cần kiểm tra trang gốc.")
    return warnings
