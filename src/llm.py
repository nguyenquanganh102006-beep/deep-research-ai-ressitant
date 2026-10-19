"""Grounded Ollama chat with citation checks against retrieved pages."""

from __future__ import annotations

import re
import time
from typing import Any

from config import (
    MAX_EVIDENCE_CHARS,
    MODEL_NAME,
    NUM_CTX,
    NUM_PREDICT,
    OLLAMA_HOST,
    OLLAMA_TIMEOUT_SECONDS,
    TEMPERATURE,
)

_CITATION = re.compile(r"\[(?:Trang|Page)\s+(\d+)\]", re.IGNORECASE)


def ollama_client() -> Any:
    import ollama

    return ollama.Client(host=OLLAMA_HOST, timeout=OLLAMA_TIMEOUT_SECONDS)


def check_ollama() -> tuple[bool, str]:
    try:
        client = ollama_client()
        response = client.list()
        models = getattr(response, "models", []) or []
        names = [getattr(model, "model", "") or getattr(model, "name", "") for model in models]
        detail = f"Ollama đang chạy; tìm thấy {len(names)} model."
        if names and not any(name == MODEL_NAME or name.startswith(MODEL_NAME + ":") for name in names):
            detail += f" Chưa thấy {MODEL_NAME}; hãy chạy ollama pull {MODEL_NAME}."
        return True, detail
    except Exception as exc:
        return False, f"Không kết nối được Ollama tại {OLLAMA_HOST}: {exc}"


def answer_question(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    context = _format_evidence(evidence)
    system_prompt = """You are a local research paper assistant.
Use only the supplied PDF evidence for facts about the paper. If the evidence does not answer the question, say clearly that the supplied evidence does not specify it. Do not fill in missing equations, identifiers, code, hyperparameters, datasets, results, or explanations from general knowledge. Do not add likely, typical, or textbook details.
Preserve mathematical symbols, formulas, code, variable names, and tensor shapes as extracted. If extraction looks corrupted or incomplete, state that and ask the reader to check the cited PDF page. Format code with fenced blocks and math with LaTeX when supported by the evidence.
Write in the user's language and keep the answer concise. Every substantive paper-specific sentence must end with a citation using only page numbers present in the evidence, formatted exactly as [Trang N]. If the evidence explicitly says something was not reported, cite that statement. Label any interpretation beyond a direct statement as your interpretation."""
    user_prompt = (
        f"QUESTION\n{question.strip()}\n\n"
        f"PDF EVIDENCE\n{context}\n\n"
        "Answer briefly from this evidence only. Do not invent page citations or add facts that are only generally plausible. If a detail is absent, say it is not stated and stop."
    )

    started = time.perf_counter()
    response = ollama_client().chat(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        think=False,
        options={
            "num_ctx": NUM_CTX,
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
        },
        stream=False,
    )
    latency = time.perf_counter() - started
    answer = str(response.message.content or "").strip()
    evidence_pages = {
        page
        for item in evidence
        for page in range(int(item["page_start"]), int(item["page_end"]) + 1)
    }
    citations = [int(value) for value in _CITATION.findall(answer)]
    invalid_citations = sorted(set(citations) - evidence_pages)
    return {
        "answer": answer,
        "latency_seconds": round(latency, 3),
        "ollama_total_seconds": round(response.total_duration / 1_000_000_000, 3)
        if response.total_duration
        else None,
        "prompt_eval_count": response.prompt_eval_count,
        "eval_count": response.eval_count,
        "citations": sorted(set(citations)),
        "evidence_pages": sorted(evidence_pages),
        "invalid_citations": invalid_citations,
        "citation_warning": (
            "Model đã dẫn trang không nằm trong đoạn nguồn được truy xuất."
            if invalid_citations
            else "Model chưa đưa citation theo mẫu [Trang N]."
            if not citations
            else ""
        ),
    }


def _format_evidence(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return "Không truy xuất được đoạn nguồn nào."
    per_item_limit = max(500, MAX_EVIDENCE_CHARS // len(evidence))
    sections: list[str] = []
    for item in evidence:
        page_start = int(item["page_start"])
        page_end = int(item["page_end"])
        page_label = str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
        section = item.get("section") or "(không có tiêu đề mục)"
        kind = item.get("type") or "text"
        text = str(item.get("content") or "").strip()
        context_truncated = False
        if len(text) > per_item_limit:
            text = text[:per_item_limit].rsplit("\n", 1)[0].rstrip()
            if text.startswith(("```", "~~~")) and text.count(text[:3]) % 2:
                text += "\n" + text[:3]
            context_truncated = True
        warnings = item.get("parse_warning") or []
        if context_truncated:
            warnings = [*warnings, "Đoạn nguồn đã được cắt để vừa context; hãy đối chiếu bản đầy đủ bên dưới."]
        warning_line = "\nParser warning: " + "; ".join(warnings) if warnings else ""
        sections.append(
            f"[Chunk {item.get('chunk_id')} | Trang {page_label} | "
            f"Section: {section} | type={kind}]{warning_line}\n{text}"
        )
    return "\n\n---\n\n".join(sections)
