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


def render_evidence_pages(
    pdf_path: Path,
    evidence: list[dict[str, Any]],
    *,
    question: str | None = None,
    max_pages: int = 2,
) -> list[tuple[int, bytes]]:
    """Render focused source pages for visual math/code checking."""
    import pymupdf

    document = pymupdf.open(pdf_path)
    try:
        anchored_page = _anchored_pdf_page(document, question or "")
        page_numbers: list[int] = (
            [anchored_page] if anchored_page is not None else []
        )
        if not page_numbers:
            for item in evidence:
                page_number = int(item["page_start"])
                if page_number not in page_numbers:
                    page_numbers.append(page_number)
                if len(page_numbers) >= max_pages:
                    break
        rendered: list[tuple[int, bytes]] = []
        for page_number in page_numbers:
            if 1 <= page_number <= document.page_count:
                page = document.load_page(page_number - 1)
                clip = _anchor_clip(page, question or "")
                scale = 2.0 if clip is not None else 1.15
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(scale, scale),
                    clip=clip,
                    alpha=False,
                )
                rendered.append((page_number, pixmap.tobytes("png")))
        return rendered
    finally:
        document.close()


def _anchored_pdf_page(document: Any, question: str) -> int | None:
    """Find a specifically requested algorithm/theorem/equation in the original PDF."""
    details = _question_anchor(question)
    if details is None:
        return None
    label, number, label_pattern = details
    target = (
        re.compile(rf"\b{re.escape(number)}\b", re.IGNORECASE)
        if label == "section"
        else re.compile(
            rf"\b{label_pattern}\s*\(?\s*{re.escape(number)}\s*\)?\b",
            re.IGNORECASE,
        )
    )
    candidates: list[tuple[int, int]] = []
    for page_index in range(document.page_count):
        folded = re.sub(
            r"\s+", " ", document.load_page(page_index).get_text("text", sort=True)
        ).casefold()
        best_score = -10
        for match in target.finditer(folded):
            before = folded[max(0, match.start() - 24) : match.start()]
            after = folded[match.end() : match.end() + 32].lstrip()
            score = 1
            if re.match(r"^(?::|\.\s*)?\s*(?:adam|flashattention|forward pass|backward pass|our proposed)", after):
                score += 5
            if re.match(r"^line\s+\d+", after):
                score -= 4
            if re.search(r"proof of\s*$", before):
                score -= 6
            best_score = max(best_score, score)
        if best_score >= 0:
            candidates.append((best_score, page_index + 1))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1]


def _question_anchor(question: str) -> tuple[str, str, str] | None:
    section = re.search(
        r"\b(?:appendix|section)\s+([A-H]\.\d+(?:\.\d+)?)\b",
        question,
        re.IGNORECASE,
    )
    if section:
        number = section.group(1)
        return "section", number, re.escape(number)
    match = re.search(
        r"\b(algorithm|alg\.?|theorem|lemma|proposition|equation|eq\.?)\s*\(?\s*(\d+(?:\.\d+)?)\s*\)?",
        question,
        re.IGNORECASE,
    )
    if not match:
        return None
    label = match.group(1).casefold().rstrip(".")
    label = {"alg": "algorithm", "eq": "equation"}.get(label, label)
    label_pattern = {
        "algorithm": r"(?:algorithm|alg\.?)",
        "equation": r"(?:equation|eq\.?)",
    }.get(label, re.escape(label))
    return label, match.group(2), label_pattern


def _anchor_clip(page: Any, question: str) -> Any | None:
    """Crop an anchored math/code region so small PDF notation remains legible."""
    import pymupdf

    details = _question_anchor(question)
    if details is None:
        return None
    label, number, label_pattern = details
    blocks = page.get_text("blocks", sort=True)
    if label == "algorithm":
        heading = re.compile(
            rf"^\s*{label_pattern}\s*{re.escape(number)}\b", re.IGNORECASE
        )
        start_index = next(
            (index for index, block in enumerate(blocks) if heading.search(str(block[4]))),
            None,
        )
        if start_index is None:
            return None
        end_index = next(
            (
                index
                for index in range(start_index + 1, len(blocks))
                if re.search(r"\breturn\s+(?:O|θ)", str(blocks[index][4]), re.IGNORECASE)
            ),
            None,
        )
        if end_index is None:
            return None
        selected = blocks[start_index : end_index + 1]
        x0 = min(float(block[0]) for block in selected)
        y0 = float(selected[0][1])
        x1 = max(float(block[2]) for block in selected)
        y1 = max(float(block[3]) for block in selected)
    elif label in {"theorem", "lemma", "proposition"}:
        heading = re.compile(
            rf"\b{label}\s*{re.escape(number)}\s*\.", re.IGNORECASE
        )
        target_block = next(
            (block for block in blocks if heading.search(str(block[4]))), None
        )
        if target_block is None:
            return None
        x0, y0, x1, y1 = map(float, target_block[:4])
    elif label == "equation":
        matches = page.search_for(f"({number})")
        if not matches:
            return None
        match = min(matches, key=lambda rect: (rect.y0, rect.x0))
        x0, y0, x1, y1 = page.rect.x0, match.y0 - 18, page.rect.x1, match.y1 + 18
    elif label == "section":
        query_terms = {
            term
            for term in re.findall(r"[a-z0-9]+", question.casefold())
            if len(term) >= 4
            and term not in {"appendix", "section", "flashattention", "forward", "backward"}
        }
        scored_blocks = [
            (
                sum(
                    term in set(re.findall(r"[a-z0-9]+", str(block[4]).casefold()))
                    for term in query_terms
                )
                + 3
                * (
                    "dropout mask" in question.casefold()
                    and "dropout mask" in str(block[4]).casefold()
                ),
                block,
            )
            for block in blocks
        ]
        score, target_block = max(scored_blocks, key=lambda item: item[0], default=(0, None))
        if target_block is None or score == 0:
            section_heading = re.compile(rf"\b{re.escape(number)}\b", re.IGNORECASE)
            target_block = next(
                (block for block in blocks if section_heading.search(str(block[4]))), None
            )
        if target_block is None:
            return None
        x0, y0, x1, y1 = map(float, target_block[:4])
    else:
        return None

    margin_x = 8 if label == "algorithm" else 12
    margin_y = 8 if label == "algorithm" else 10
    return pymupdf.Rect(
        max(page.rect.x0, x0 - margin_x),
        max(page.rect.y0, y0 - margin_y),
        min(page.rect.x1, x1 + margin_x),
        min(page.rect.y1, y1 + margin_y),
    )


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
