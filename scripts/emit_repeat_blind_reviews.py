"""Append validated AI review receipts for frozen, model-blind repeat packets."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


_CITATION = re.compile(r"\[(?:Trang|Page)\s+(\d+)(?:\s*[-–—]\s*(\d+))?\]", re.I)
_BOOL_FIELDS = ("citation_supported", "formula_fidelity", "algorithm_reasoning",
                "numeric_protocol_accuracy", "correct_abstention", "false_refusal")


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _validate_decision(decision: dict):
    score = decision.get("correctness")
    if isinstance(score, bool) or score not in (0, 0.5, 1):
        raise ValueError(f"Invalid correctness score: {score!r}")
    for field in _BOOL_FIELDS:
        value = decision.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"Invalid review field {field}: {value!r}")
    if not isinstance(decision.get("claims"), list):
        raise ValueError("claims must be a list")
    for claim in decision["claims"]:
        if not isinstance(claim.get("text"), str) or len(claim["text"]) > 240:
            raise ValueError("claim text must be a string of at most 240 characters")
        if claim.get("supported") is not None and not isinstance(claim.get("supported"), bool):
            raise ValueError("claim supported must be bool or null")
        if claim.get("source") not in ("question", "evidence", "none"):
            raise ValueError("claim source must be question, evidence, or none")
        if not isinstance(claim.get("cited_pages"), list):
            raise ValueError("claim cited_pages must be a list")
        if not isinstance(claim.get("reason"), str):
            raise ValueError("claim reason must be a string")


def emit(packet_path: Path, output_path: Path, decisions: dict[str, dict], protocol_path: Path,
         reviewer="primary_assistant_gpt6", judge_model="GPT-6 (primary assistant; exact variant not exposed)",
         reasoning_effort="not exposed", reviewed_at: str | None = None):
    packets = _read_jsonl(packet_path)
    packet_by_id = {row["review_id"]: row for row in packets}
    if len(packet_by_id) != len(packets):
        raise ValueError(f"Duplicate review_id in blind packet: {packet_path}")
    unknown = set(decisions) - set(packet_by_id)
    if unknown:
        raise ValueError(f"Decision IDs not found in packet: {sorted(unknown)}")

    previous = _read_jsonl(output_path) if output_path.exists() else []
    existing = {row["review_id"]: row for row in previous}
    if len(existing) != len(previous):
        raise ValueError(f"Duplicate review_id in existing sidecar: {output_path}")
    protocol_sha = hashlib.sha256(protocol_path.read_bytes()).hexdigest()
    now = reviewed_at or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()
    new_rows = []
    for rid, decision in decisions.items():
        _validate_decision(decision)
        packet = packet_by_id[rid]
        cited_pages = set()
        for start, end in _CITATION.findall(packet.get("model_answer", "")):
            a, b = int(start), int(end or start)
            cited_pages.update(range(min(a, b), max(a, b) + 1))
        allowed = set(packet.get("allowed_pages", []))
        for claim in decision["claims"]:
            if set(claim["cited_pages"]) - allowed:
                raise ValueError(f"Claim citation outside allowed_pages for {rid}")
        citation = decision.get("citation_supported")
        if cited_pages and citation is None:
            raise ValueError(f"Concrete citation requires a supported/unsupported label for {rid}")
        if cited_pages - allowed and citation is not False:
            raise ValueError(f"Citation outside allowed_pages must be unsupported for {rid}")
        receipt = {
            "review_id": rid,
            "question_id": packet["question_id"],
            "category": packet["category"],
            "correctness": decision["correctness"],
            "citation_supported": citation,
            "primary_error": decision.get("primary_error"),
            "notes": decision["notes"],
            "claims": decision["claims"],
            "formula_fidelity": decision.get("formula_fidelity"),
            "algorithm_reasoning": decision.get("algorithm_reasoning"),
            "numeric_protocol_accuracy": decision.get("numeric_protocol_accuracy"),
            "correct_abstention": decision.get("correct_abstention"),
            "false_refusal": decision.get("false_refusal", False),
            "reviewer": reviewer,
            "provenance": {
                "judge_model": judge_model,
                "reasoning_effort": reasoning_effort,
                "review_type": "AI only, not human/expert gold",
                "judge_protocol_sha256": protocol_sha,
            },
            "reviewed_at": now,
            "input_sha256": packet["input_sha256"],
            "evidence_sha256": packet["evidence_sha256"],
            "packet_sha256": packet["packet_sha256"],
            "source_prediction_line_sha256_including_line_ending": packet[
                "source_prediction_line_sha256_including_line_ending"],
            "output_truncated": bool(packet.get("output_truncated")),
        }
        if rid in existing:
            if existing[rid] != receipt:
                raise ValueError(f"Refusing to alter existing receipt: {rid}")
            continue
        new_rows.append(receipt)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if new_rows:
        content = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n" for row in new_rows).encode("utf-8")
        with output_path.open("ab") as stream:
            stream.write(content)
    return {"packet_count": len(packets), "decision_count": len(decisions),
            "existing_receipts": len(existing), "new_receipts": len(new_rows),
            "output": str(output_path), "protocol_sha256": protocol_sha}
