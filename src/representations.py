"""Loss-aware text, math, and code representations for source inspection."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_GREEK_LATEX = {
    "α": r"\alpha",
    "β": r"\beta",
    "γ": r"\gamma",
    "δ": r"\delta",
    "ε": r"\epsilon",
    "ζ": r"\zeta",
    "η": r"\eta",
    "θ": r"\theta",
    "ι": r"\iota",
    "κ": r"\kappa",
    "λ": r"\lambda",
    "μ": r"\mu",
    "ν": r"\nu",
    "ξ": r"\xi",
    "π": r"\pi",
    "ρ": r"\rho",
    "σ": r"\sigma",
    "τ": r"\tau",
    "φ": r"\phi",
    "χ": r"\chi",
    "ψ": r"\psi",
    "ω": r"\omega",
    "Γ": r"\Gamma",
    "Δ": r"\Delta",
    "Θ": r"\Theta",
    "Λ": r"\Lambda",
    "Ξ": r"\Xi",
    "Π": r"\Pi",
    "Σ": r"\Sigma",
    "Φ": r"\Phi",
    "Ψ": r"\Psi",
    "Ω": r"\Omega",
}
_LATEX_SYMBOLS = {
    "←": r"\leftarrow",
    "→": r"\to",
    "≤": r"\leq",
    "≥": r"\geq",
    "≠": r"\neq",
    "≈": r"\approx",
    "∈": r"\in",
    "∉": r"\notin",
    "∞": r"\infty",
    "∑": r"\sum",
    "∏": r"\prod",
    "∇": r"\nabla",
    "∂": r"\partial",
    "⊙": r"\odot",
    "⊗": r"\otimes",
    "⊤": r"^\top",
    "·": r"\cdot",
    "×": r"\times",
    "−": "-",
    "–": "-",
}
_SUBSCRIPT = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "₊": "+", "₋": "-", "₌": "=", "₍": "(", "₎": ")",
    "ₐ": "a", "ₑ": "e", "ₕ": "h", "ᵢ": "i", "ⱼ": "j",
    "ₖ": "k", "ₗ": "l", "ₘ": "m", "ₙ": "n", "ₒ": "o",
    "ₚ": "p", "ᵣ": "r", "ₛ": "s", "ₜ": "t", "ᵤ": "u",
    "ᵥ": "v", "ₓ": "x",
}
_SUPERSCRIPT = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
    "⁺": "+", "⁻": "-", "⁼": "=", "⁽": "(", "⁾": ")",
    "ⁿ": "n", "ⁱ": "i",
}
_MATH_MARKERS = re.compile(
    r"(?:[α-ωΑ-Ω]|[\u2200-\u22ff]|[\u2070-\u209f]|"
    r"[\U0001d400-\U0001d7ff]|\\(?:frac|sqrt|sum|theta|beta)|"
    r"\$\$?|\b(?:Eq(?:uation)?\.?\s*\(?\d+)|"
    r"[A-Za-z]\w*(?:[_^]\{?[A-Za-z0-9-]+\}?)?\s*(?:=|:=|≈|≤|≥))",
    re.IGNORECASE,
)
_SOURCE_LATEX = re.compile(r"\\(?:begin|frac|sqrt|sum|theta|beta)|\$", re.IGNORECASE)


def looks_like_math(text: str) -> bool:
    return bool(_MATH_MARKERS.search(text))


def looks_like_code(text: str) -> bool:
    if re.match(r"^\s*(```|~~~)", text):
        return True
    has_algorithm = bool(re.search(r"\bAlgorithm\s+\d+\b", text, re.IGNORECASE))
    has_algorithm_lines = bool(
        re.search(r"\bRequire:|\bInitialize\b|\bwhile\b.{0,80}\bdo\b", text, re.IGNORECASE)
        or len(re.findall(r"(?m)^\s*\d+\s*:", text)) >= 2
    )
    return has_algorithm and has_algorithm_lines


def build_representations(text: str, kind: str) -> dict[str, Any]:
    """Keep extracted content verbatim and derive explicitly unverified helpers."""
    math_like = kind in {"math", "mixed"} or looks_like_math(text)
    code_like = kind == "code" or looks_like_code(text)
    latex_candidate = (
        _latex_candidate(text)
        if math_like and not code_like and _is_compact_formula(text)
        else None
    )
    has_source_latex = bool(_SOURCE_LATEX.search(text))
    return {
        "raw_text": text,
        "latex_candidate": latex_candidate,
        "latex_status": (
            "source_latex" if has_source_latex else "heuristic_unverified"
        ) if latex_candidate else None,
        "code_text": text if code_like else None,
        "code_kind": (
            "pseudocode" if re.search(r"\bAlgorithm\s+\d+\b", text, re.IGNORECASE)
            else "verbatim_extraction"
        ) if code_like else None,
        "visual_verification_required": math_like or code_like,
    }


def _latex_candidate(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "√":
            radicand, next_index = _sqrt_radicand(text, index + 1)
            if radicand:
                output.append(r"\sqrt{" + _latex_candidate(radicand) + "}")
                index = next_index
                continue
        if char in _SUBSCRIPT or char in _SUPERSCRIPT:
            next_kind = "sub" if char in _SUBSCRIPT else "super"
            script_chars: list[str] = []
            while index < len(text):
                script_char = text[index]
                script_map = _SUBSCRIPT if next_kind == "sub" else _SUPERSCRIPT
                if script_char not in script_map:
                    break
                script_chars.append(script_map[script_char])
                index += 1
            marker = "_" if next_kind == "sub" else "^"
            output.append(f"{marker}{{{''.join(script_chars)}}}")
            continue
        normalized = unicodedata.normalize("NFKC", char)
        for normalized_char in normalized:
            replacement = _GREEK_LATEX.get(
                normalized_char,
                _LATEX_SYMBOLS.get(normalized_char, normalized_char),
            )
            output.append(replacement)
            # TeX control words end at the next non-letter; add an empty group
            # where two symbols would otherwise merge into an invalid command.
            if (
                re.fullmatch(r"\\[A-Za-z]+", replacement)
                and index + 1 < len(text)
                and text[index + 1].isalpha()
                and text[index + 1] not in _SUBSCRIPT
                and text[index + 1] not in _SUPERSCRIPT
            ):
                output.append("{}")
        index += 1
    return "".join(output)


def _is_compact_formula(text: str) -> bool:
    """Avoid pretending layout-damaged prose or Markdown is valid LaTeX."""
    candidate = text.strip()
    if not candidate or len(candidate) > 400 or candidate.count("\n") > 4:
        return False
    if re.search(r"(?m)^\s*(?:#{1,6}|>|[-*+]\s)", candidate):
        return False
    if re.search(r"\*\*|`{1,3}|\[[^\]]*\]|(?<!\\)_[^_\s][^_\n]*_", candidate):
        return False
    if len(re.findall(r"[A-Za-z]{4,}", candidate)) > 3:
        return False
    return looks_like_math(candidate)


def _sqrt_radicand(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return "", start
    opening = text[start]
    matching = {"(": ")", "{": "}"}
    if opening in matching:
        closing = matching[opening]
        depth = 0
        for index in range(start, len(text)):
            if text[index] == opening:
                depth += 1
            elif text[index] == closing:
                depth -= 1
                if depth == 0:
                    return text[start + 1:index], index + 1
        return text[start + 1:], len(text)

    end = start + 1
    while end < len(text) and (
        unicodedata.category(text[end]).startswith("M")
        or text[end] in _SUBSCRIPT
        or text[end] in _SUPERSCRIPT
    ):
        end += 1
    return text[start:end], end
