"""Run a local PDF pipeline sanity check; outputs stay under the selected data root."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--questions", type=Path)
    group.add_argument("--question")
    parser.add_argument("--model")
    parser.add_argument("--all-answers", action="store_true")
    args = parser.parse_args()
    import os
    if args.model: os.environ["DEEPRESEARCH_MODEL"] = args.model
    from config import MODEL_NAME, NUM_CTX
    from src.ingest import ingest_pdf_bytes
    from src.llm import answer_question, check_ollama, needs_visual_evidence
    from src.parser import render_evidence_pages
    from src.retriever import retrieve
    from src.storage import paper_dir, append_jsonl, write_json

    metadata, reused = ingest_pdf_bytes(args.pdf.read_bytes(), args.pdf.name)
    directory = paper_dir(metadata["document_id"])
    _, repeat = ingest_pdf_bytes(args.pdf.read_bytes(), args.pdf.name)
    import subprocess
    report = {"commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
              "worktree_status": subprocess.check_output(["git", "status", "--short"], text=True),
              "model": MODEL_NAME, "num_ctx": NUM_CTX, "metadata": metadata,
              "cache_reused": reused, "repeat_cache_reused": repeat, "results": []}
    ready, detail = check_ollama()
    if not ready:
        raise RuntimeError(detail)
    seen = set()
    cases = json.loads(args.questions.read_text(encoding="utf-8")) if args.questions else [{"id": "single", "type": "text", "question": args.question}]
    for case in cases:
        started = time.perf_counter()
        matches = retrieve(metadata["document_id"], case["question"], top_k=5, max_contexts=5, include_neighbors=False)
        pages = sorted({p for m in matches for p in range(m["page_start"], m["page_end"] + 1)})
        assert all(1 <= p <= metadata["page_count"] for p in pages)
        row = {"id": case["id"], "type": case["type"], "retrieved_pages": pages,
               "retrieved_ids": [m["chunk_id"] for m in matches]}
        expected = case.get("page_ground_truth") or []
        if isinstance(expected, int): expected = [expected]
        row["hit_at_5"] = bool(set(expected) & set(pages)) if expected else None
        append_jsonl(directory / "retrieval_log.jsonl", row)
        if args.all_answers or (case["type"] in {"text", "math", "code"} and case["type"] not in seen):
            images = render_evidence_pages(directory / "source.pdf", matches, question=case["question"]) if needs_visual_evidence(case["question"], matches) else None
            row.update(answer_question(case["question"], matches, images))
            row["nonempty_answer"] = bool(row["answer"].strip())
            append_jsonl(directory / "qa_log.jsonl", row)
            seen.add(case["type"])
        row["total_seconds"] = round(time.perf_counter() - started, 3)
        report["results"].append(row)
        write_json(directory / "sanity_report.json", report)
        print(row["id"], row.get("nonempty_answer"), row.get("invalid_citations"), flush=True)
    answers = [row for row in report["results"] if "answer" in row]
    report["citation_warning_count"] = sum(bool(row.get("citation_warning")) for row in answers)
    report["functional_pass"] = repeat and all(row["nonempty_answer"] for row in answers)
    report["status"] = "PASS_WITH_WARNINGS" if report["citation_warning_count"] else "PASS"
    write_json(directory / "sanity_report.json", report)
    print(directory / "sanity_report.json", flush=True)

if __name__ == "__main__": main()
