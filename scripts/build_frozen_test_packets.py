"""Build retrieved-text packets only after the final benchmark freeze.

This entry point deliberately does not use the dev loader. It requires an
explicit, committed freeze manifest before it opens the frozen test labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import PROJECT_ROOT
from src.benchmark.evidence_packets import save_packets
from src.benchmark.local_common import (CONFIG, DATA, file_hash, fingerprint, pipeline_code_hashes,
                                        read_json, read_rows)
from src.benchmark.runner_local import messages_for


TEST_COUNT = 268
TEST_FILE = DATA / "test_frozen.jsonl"
PAPERS_FILE = DATA / "papers.jsonl"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_freeze(path: Path, protocol_path: Path):
    freeze = json.loads(path.read_text(encoding="utf-8"))
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True
    ).strip()
    if freeze.get("status") != "frozen_before_test":
        raise ValueError("Freeze manifest is not marked frozen_before_test")
    if freeze.get("candidate_commit_sha") != head:
        raise ValueError("Current HEAD does not equal the recorded candidate freeze commit")
    if freeze.get("track") != "retrieved_text_frozen":
        raise ValueError("Final test protocol must use retrieved_text_frozen")
    if freeze.get("expected_test_question_count") != TEST_COUNT:
        raise ValueError(f"Freeze must pin exactly {TEST_COUNT} test questions")
    if freeze.get("protocol_path") != protocol_path.relative_to(PROJECT_ROOT).as_posix():
        raise ValueError("Protocol path differs from the frozen manifest")
    protocol = read_json(protocol_path)
    if protocol.get("split") != "test":
        raise ValueError("Final test protocol must set split=test")
    if freeze.get("protocol_sha256") != file_hash(protocol_path):
        raise ValueError("Final test protocol hash differs from the frozen manifest")
    candidate_config = PROJECT_ROOT / freeze.get("candidate_config_path", "")
    if (not freeze.get("candidate_config_sha256")
            or file_hash(candidate_config) != freeze.get("candidate_config_sha256")):
        raise ValueError("Candidate selection config differs from the freeze manifest")
    candidate = read_json(candidate_config)
    if (candidate.get("models") != freeze.get("models")
            or candidate.get("thresholds") != freeze.get("thresholds")
            or candidate.get("benchmark_code_sha256") != freeze.get("benchmark_code_sha256")
            or candidate.get("pipeline_code_sha256") != freeze.get("pipeline_code_sha256")
            or candidate.get("phase6_code_sha256") != freeze.get("phase6_code_sha256")
            or candidate.get("protocol_path") != freeze.get("protocol_path")
            or candidate.get("protocol_sha256") != freeze.get("protocol_sha256")
            or candidate.get("retrieval") != freeze.get("retrieval")):
        raise ValueError("Frozen models, thresholds, or protocol differ from candidate selection")
    phase6_code = {rel: file_hash(PROJECT_ROOT / rel) for rel in candidate.get("phase6_code_sha256", {})}
    if not phase6_code or phase6_code != freeze.get("phase6_code_sha256"):
        raise ValueError("Final test preparation/scoring code changed after freeze")
    current_code = {path.relative_to(PROJECT_ROOT).as_posix(): file_hash(path) for path in
                    sorted((PROJECT_ROOT / "src/benchmark").glob("*.py"))}
    if current_code != freeze.get("benchmark_code_sha256"):
        raise ValueError("Benchmark source code changed after candidate freeze")
    if pipeline_code_hashes() != freeze.get("pipeline_code_sha256"):
        raise ValueError("PDF ingestion/retrieval pipeline changed after candidate freeze")
    if freeze.get("prompt_sha256") != file_hash(CONFIG / "prompt_v1.txt"):
        raise ValueError("Prompt hash differs from the freeze manifest")
    judge_protocol_path = PROJECT_ROOT / freeze.get("judge_protocol_path", "")
    if file_hash(judge_protocol_path) != freeze.get("judge_protocol_sha256"):
        raise ValueError("Judge protocol hash differs from the freeze manifest")
    if candidate.get("prompt_sha256") != freeze.get("prompt_sha256") or candidate.get("judge_protocol_sha256") != freeze.get("judge_protocol_sha256"):
        raise ValueError("Prompt or judge protocol differs from candidate selection")
    expected_models = freeze.get("models")
    if not isinstance(expected_models, list) or not expected_models:
        raise ValueError("Freeze manifest must list the selected candidate and baseline models")
    return freeze, protocol


def build(freeze_path: Path, protocol_path: Path, output: Path):
    freeze_path = freeze_path.resolve()
    protocol_path = protocol_path.resolve()
    output = output.resolve()
    freeze, protocol = _verify_freeze(freeze_path, protocol_path)

    # This is the first point where the sealed test labels are opened.
    test_raw = TEST_FILE.read_bytes()
    test_sha = hashlib.sha256(test_raw).hexdigest()
    expected_sha = freeze.get("test_frozen_sha256")
    if not expected_sha:
        raise ValueError("Record the frozen test hash after candidate commit and before packet generation")
    if expected_sha != test_sha:
        raise ValueError("Frozen test dataset hash differs from the freeze manifest")
    questions = [json.loads(line.decode("utf-8")) for line in test_raw.splitlines() if line.strip()]
    qids = [row.get("question_id") for row in questions]
    if len(questions) != TEST_COUNT or len(set(qids)) != TEST_COUNT:
        raise ValueError(f"Expected {TEST_COUNT} unique frozen test questions")
    if any(row.get("split") not in ("test", "test_frozen") for row in questions):
        raise ValueError("Frozen test file contains a non-test question")
    if any(not row.get("question") or not row.get("paper_ids") or not row.get("category")
           for row in questions):
        raise ValueError("Frozen test question is missing required input metadata")

    papers_raw = PAPERS_FILE.read_bytes()
    papers = {row["paper_id"]: row for row in read_rows(PAPERS_FILE)}
    protocol_bytes = protocol_path.read_bytes()
    prompt = (CONFIG / "prompt_v1.txt").read_text(encoding="utf-8")
    top_k = int(protocol["retrieval_top_k"])
    max_source_pages = int(freeze["retrieval"]["max_source_pages"])
    if max_source_pages < 1:
        raise ValueError("Frozen retrieval page allowance must be positive")
    from src.ingest import ingest_pdf_bytes
    from src.retriever import retrieve

    parsed = {}
    packets = []
    for question in questions:
        evidence = []
        for paper_id in question["paper_ids"]:
            paper = papers.get(paper_id)
            if paper is None:
                raise ValueError(f"Unknown paper in frozen test: {paper_id}")
            source = PROJECT_ROOT / paper["pdf_path"]
            if paper_id not in parsed:
                if file_hash(source) != paper["pdf_sha256"]:
                    raise ValueError(f"PDF hash mismatch for frozen test paper {paper_id}")
                parsed[paper_id], _ = ingest_pdf_bytes(
                    source.read_bytes(), source.name, max_pages=max_source_pages
                )
            for chunk in retrieve(parsed[paper_id]["document_id"], question["question"],
                                  top_k=top_k, max_contexts=top_k, include_neighbors=False):
                evidence.append({
                    "paper_id": paper_id, "pdf_sha256": paper["pdf_sha256"],
                    "chunk_id": chunk["chunk_id"], "page_start": chunk["page_start"],
                    "page_end": chunk["page_end"], "content": chunk["content"],
                    "dense_score": chunk["dense_score"], "bm25_score": chunk["bm25_score"],
                    "rrf_score": chunk["rrf_score"],
                })
        images = []
        packet = {
            "schema_version": 1, "track": "retrieved_text_frozen", "split": "test",
            "question_id": question["question_id"], "question": question["question"],
            "paper_ids": question["paper_ids"], "category": question["category"],
            "evidence": evidence, "images": images,
            "retrieval_provenance": {
                paper_id: {key: parsed[paper_id].get(key) for key in
                           ("document_id", "parser_version", "ingestion_fingerprint",
                            "embedding_model", "embedding_fingerprint", "embedding_dimensions")}
                for paper_id in question["paper_ids"]
            },
            "source_evidence_sha256": fingerprint({"evidence": evidence, "images": images}),
            "gold_evidence_status": "not_applicable", "verification_receipt": None,
        }
        packet["evidence_sha256"] = fingerprint({"evidence": evidence, "images": images})
        packet["packet_sha256"] = fingerprint(packet)
        if {"reference_answer", "expected_reasoning_checks", "answer", "rubric"} & set(packet):
            raise ValueError("Test gold answer or rubric leaked into model packet")
        # Refuse to freeze a packet the common Track B protocol cannot send intact.
        messages_for(packet, prompt, protocol)
        packets.append(packet)

    manifest_path = output.with_suffix(".manifest.json")
    if output.exists() or manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite final test packets/manifest: {output}")
    result = save_packets(packets, output)
    packet_manifest = read_json(manifest_path)
    packet_manifest.update({
        "split": "test", "track": "retrieved_text_frozen",
        "freeze_manifest_sha256": _sha(freeze_path),
        "candidate_commit_sha": freeze["candidate_commit_sha"],
        "test_frozen_sha256": test_sha, "papers_manifest_sha256": hashlib.sha256(papers_raw).hexdigest(),
        "protocol_sha256": hashlib.sha256(protocol_bytes).hexdigest(),
        "retrieval_top_k": top_k, "label_fields_excluded": True,
    })
    manifest_path.write_text(json.dumps(packet_manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return {"packets": result["packets"], "sha256": result["sha256"],
            "test_frozen_sha256": test_sha, "manifest": str(manifest_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-manifest", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, default=CONFIG / "final_test_protocol_v1.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.freeze_manifest, args.protocol, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
