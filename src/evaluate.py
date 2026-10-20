"""Manual benchmark runner for a paper-specific tests/questions.json file."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import PROJECT_ROOT
from src.llm import answer_question, needs_visual_evidence
from src.parser import render_evidence_pages
from src.retriever import retrieve
from src.storage import list_documents, paper_dir, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-id", help="64-character SHA-256 ID; defaults to the latest indexed PDF")
    parser.add_argument(
        "--questions",
        type=Path,
        default=PROJECT_ROOT / "tests" / "questions.json",
        help="Question dataset JSON",
    )
    parser.add_argument("--answer", action="store_true", help="Also ask Ollama to answer each question")
    args = parser.parse_args()

    documents = list_documents()
    document_id = args.document_id
    if not document_id:
        available = [item for item in documents if item.get("parse_status") in {"ok", "warning"}]
        if not available:
            parser.error("No indexed PDF found. Process a PDF in app.py first.")
        document_id = available[0]["document_id"]
    test_cases = read_json(args.questions)
    if not isinstance(test_cases, list):
        parser.error("Question file must contain a JSON array.")

    results: list[dict[str, Any]] = []
    for case in test_cases:
        if not isinstance(case, dict) or not case.get("question"):
            continue
        question_id = case.get("id", f"q{len(results) + 1}")
        try:
            matches = retrieve(
                document_id,
                case["question"],
                top_k=5,
                max_contexts=5,
                include_neighbors=False,
            )
            retrieved_pages = sorted(
                {
                    page
                    for item in matches
                    for page in range(int(item["page_start"]), int(item["page_end"]) + 1)
                }
            )
            expected_pages = case.get("page_ground_truth")
            if isinstance(expected_pages, int):
                expected_pages = [expected_pages]
            hit = (
                None
                if not expected_pages
                else bool(set(expected_pages).intersection(retrieved_pages))
            )
            result: dict[str, Any] = {
                "id": question_id,
                "type": case.get("type", "unknown"),
                "question": case["question"],
                "retrieved_pages": retrieved_pages,
                "retrieved_ids": [item["chunk_id"] for item in matches],
                "expected_pages": expected_pages,
                "hit_at_5": hit,
                "error_class": "retrieval_miss" if hit is False else None,
            }
            if args.answer:
                source_images = (
                    render_evidence_pages(
                        paper_dir(document_id) / "source.pdf",
                        matches,
                        question=case["question"],
                    )
                    if needs_visual_evidence(case["question"], matches)
                    else None
                )
                answer_result = answer_question(case["question"], matches, source_images)
                result["answer"] = answer_result["answer"]
                result["latency_seconds"] = answer_result["latency_seconds"]
                result["citation_warning"] = answer_result["citation_warning"]
                result["citations"] = answer_result["citations"]
                result["invalid_citations"] = answer_result["invalid_citations"]
                if answer_result["invalid_citations"] or answer_result["citation_warning"]:
                    result["error_class"] = "citation_error"
                elif not result["error_class"]:
                    result["error_class"] = "requires_manual_answer_review"
            results.append(result)
            print(
                f"{question_id}: Hit@5={hit if hit is not None else 'ground truth missing'}, "
                f"pages={retrieved_pages}"
            )
        except Exception as exc:
            results.append(
                {
                    "id": question_id,
                    "question": case["question"],
                    "error_class": "parse_or_retrieval_error",
                    "error": str(exc),
                }
            )
            print(f"{question_id}: error: {exc}")

    measurable = [result for result in results if result.get("hit_at_5") is not None]
    report = {
        "document_id": document_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "question_count": len(results),
        "grounded_question_count": len(measurable),
        "hit_at_5": (
            sum(bool(result["hit_at_5"]) for result in measurable) / len(measurable)
            if measurable
            else None
        ),
        "results": results,
    }
    report_dir = paper_dir(document_id) / "evaluations"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"evaluation-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    write_json(report_path, report)
    print(f"\nReport saved to: {report_path}")
    if report["hit_at_5"] is None:
        print("Hit@5 was not measured: fill page_ground_truth in the question dataset first.")
    else:
        print(f"Hit@5: {report['hit_at_5']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
