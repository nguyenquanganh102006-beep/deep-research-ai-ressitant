"""Markdown-aware chunking that keeps detected code and math blocks together."""

from __future__ import annotations

import re
from typing import Any

from config import CHUNK_MAX_WORDS, CHUNK_OVERLAP_WORDS, CHUNK_TARGET_WORDS
from src.representations import build_representations

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_MATH_START = re.compile(r"^\s*(\$\$|\\\[|\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|cases))")


def create_chunks(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for page in pages:
        page_number = int(page["page_number"])
        warnings = list(page.get("parser_warning") or [])
        blocks = _split_markdown_blocks(str(page.get("markdown") or ""))
        section = ""
        prepared: list[dict[str, str]] = []
        for block in blocks:
            heading = _HEADING.match(block.strip().splitlines()[0]) if block.strip() else None
            if heading:
                section = heading.group(1).strip()
            for part in _fit_blocks(block):
                prepared.append({"content": part, "type": _classify(part)})

        current: list[dict[str, str]] = []
        current_words = 0
        previous_overlap = ""
        page_chunk_index = 0

        def flush() -> None:
            nonlocal current, current_words, previous_overlap, page_chunk_index
            if not current:
                return
            content_parts = [part["content"] for part in current]
            content = "\n\n".join(content_parts).strip()
            labels = {part["type"] for part in current}
            if "mixed" in labels or ("code" in labels and "text" in labels) or (
                "math" in labels and ("text" in labels or "code" in labels)
            ):
                kind = "mixed"
            elif "code" in labels:
                kind = "code"
            elif "math" in labels:
                kind = "math"
            else:
                kind = "text"
            page_chunk_index += 1
            chunks.append(
                {
                    "chunk_id": f"p{page_number:04d}-c{page_chunk_index:03d}",
                    "page_start": page_number,
                    "page_end": page_number,
                    "section": section,
                    "type": kind,
                    "content": content,
                    "representations": build_representations(content, kind),
                    "equation_id": _equation_id(content),
                    "parse_warning": warnings,
                }
            )
            # Overlap only ordinary prose. Code and equations remain intact in
            # their source chunk, with neighboring chunks available at retrieval.
            last = current[-1]
            if last["type"] == "text":
                words = last["content"].split()
                previous_overlap = " ".join(words[-CHUNK_OVERLAP_WORDS:])
            else:
                previous_overlap = ""
            current = []
            current_words = 0

        for block in prepared:
            word_count = len(block["content"].split())
            if current and current_words + word_count > CHUNK_TARGET_WORDS:
                flush()
                if previous_overlap and block["type"] == "text":
                    current.append({"content": previous_overlap, "type": "text"})
                    current_words += len(previous_overlap.split())
            current.append(block)
            current_words += word_count
            if current_words >= CHUNK_MAX_WORDS:
                flush()
        flush()

    return chunks


def _split_markdown_blocks(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    blocks: list[str] = []
    current: list[str] = []
    state: str | None = None
    fence_char = ""
    math_environment = ""

    def emit() -> None:
        nonlocal current
        text = "\n".join(current).strip()
        if text:
            blocks.append(text)
        current = []

    for line in lines:
        fence_match = _FENCE.match(line)
        if state == "code":
            current.append(line)
            if fence_match and fence_match.group(1)[0] == fence_char:
                emit()
                state = None
            continue
        if state == "math":
            current.append(line)
            if math_environment:
                if f"\\end{{{math_environment}}}" in line:
                    emit()
                    state = None
                    math_environment = ""
            elif "$$" in line or r"\]" in line:
                emit()
                state = None
            continue

        if fence_match:
            emit()
            state = "code"
            fence_char = fence_match.group(1)[0]
            current.append(line)
            continue

        math_match = _MATH_START.match(line)
        if math_match:
            emit()
            state = "math"
            math_environment = math_match.group(2) or ""
            current.append(line)
            if not math_environment and (
                (line.count("$$") >= 2) or r"\]" in line
            ):
                emit()
                state = None
            continue

        if not line.strip():
            emit()
        else:
            current.append(line)
    emit()
    return blocks


def _fit_blocks(block: str) -> list[str]:
    if len(block.split()) <= CHUNK_MAX_WORDS:
        return [block]

    # Preserve line breaks and indentation for large code blocks. Split only
    # between lines, and keep oversized single lines intact.
    lines = block.splitlines()
    is_code = bool(lines and _FENCE.match(lines[0]))
    if is_code:
        opening = lines[0]
        fence_char = _FENCE.match(opening).group(1)[0]
        has_closing_fence = len(lines) > 1 and bool(_FENCE.match(lines[-1])) and _FENCE.match(lines[-1]).group(1)[0] == fence_char
        interior = lines[1:-1] if has_closing_fence else lines[1:]
        closing = lines[-1] if has_closing_fence else fence_char * 3
        code_parts: list[str] = []
        current: list[str] = []
        count = 0
        for line in interior:
            line_words = len(line.split())
            if current and count + line_words > CHUNK_TARGET_WORDS:
                code_parts.append(opening + "\n" + "\n".join(current) + "\n" + closing)
                current, count = [], 0
            current.append(line)
            count += line_words
        if current:
            code_parts.append(opening + "\n" + "\n".join(current) + "\n" + closing)
        return code_parts or [opening + "\n" + closing]

    words = block.split()
    return [
        " ".join(words[start : start + CHUNK_TARGET_WORDS])
        for start in range(0, len(words), CHUNK_TARGET_WORDS)
    ]


def _classify(text: str) -> str:
    stripped = text.strip()
    if _FENCE.match(stripped.splitlines()[0] if stripped else ""):
        return "code"
    if re.search(r"\b(?:Algorithm|Pseudocode)\s*\d+\b", text, re.IGNORECASE) and re.search(
        r"(?m)^\s*(?:Input|Output|for|while|if|return)\b", text, re.IGNORECASE
    ):
        return "code"
    if re.search(r"\bdef\s+[A-Za-z_]\w*\s*\(|\bfor\s+\w+\s+in\s+", text):
        return "code"
    if (
        "$$" in text
        or r"\[" in text
        or r"\(" in text
        or r"\begin{" in text
        or re.search(r"(?<!\\)\$[^$\n]{1,160}\$", text)
        or re.search(r"\b(?:Eq(?:uation)?\.?\s*\(?\d+|[A-Za-z]\s*=\s*[^=])", text)
    ):
        return "math"
    return "text"


def _equation_id(text: str) -> str | None:
    match = re.search(r"\b(?:Equation|Eq\.?)[\s(]*(\d+)\)?", text, re.IGNORECASE)
    return match.group(1) if match else None
