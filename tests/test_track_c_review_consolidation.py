import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.consolidate_track_c_reviews import consolidate
from src.benchmark.scoring_local import review_id


def _line(row):
    return (json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class TrackCReviewConsolidationTests(unittest.TestCase):
    def _fixture(self, root: Path):
        run_dir = root / "run"
        judging = run_dir / "judging"
        packet_dir = judging / "blind_packets_v1"
        packet_dir.mkdir(parents=True)

        prediction = {
            "run_id": "test-run", "track": "retrieved_vision", "question_id": "math-0001",
            "model_digest": "digest", "answer": "candidate", "evidence_sha256": "evidence-hash",
            "model_tag": "test-model", "category": "math", "status": "completed",
        }
        prediction_line = _line(prediction)
        (run_dir / "predictions.jsonl").write_bytes(prediction_line)
        rid = review_id(prediction)
        identity = {
            "review_id": rid, "question_id": "math-0001", "input_sha256": "input-hash",
            "packet_sha256": "packet-hash", "evidence_sha256": "evidence-hash",
            "source_prediction_line_sha256_including_line_ending": _sha(prediction_line),
        }
        packet = {**identity, "category": "math",
                  "prediction_line_sha256_including_line_ending": _sha(prediction_line)}

        category_meta = {}
        for category in ("math", "code", "table"):
            rows = [packet] if category == "math" else []
            packet_bytes = b"".join(_line(row) for row in rows)
            packet_path = packet_dir / f"{category}_v1.jsonl"
            packet_path.write_bytes(packet_bytes)
            category_meta[category] = {"count": len(rows), "sha256": _sha(packet_bytes)}
            main_path = judging / f"track_c_reviews_{category}_agent_v1.jsonl"
            if category == "math":
                main = {
                    **identity, "correctness": 0, "citation_supported": False,
                    "primary_error": "wrong_formula", "notes": "initial assessment",
                    "claims": [], "formula_fidelity": False, "algorithm_reasoning": False,
                    "numeric_protocol_accuracy": False, "reviewer": "judge_math_primary_agent",
                    "provenance": {"review_type": "AI only,not human/expert gold"},
                    "reviewed_at": "2026-11-15T10:00:00+07:00",
                }
                main_line = _line(main)
                main_path.write_bytes(main_line)
                correction = {
                    **identity, "correctness": 0.5, "citation_supported": False,
                    "primary_error": "partial", "notes": "corrected assessment", "claims": [],
                    "formula_fidelity": False, "algorithm_reasoning": False,
                    "numeric_protocol_accuracy": False, "reviewer": "judge_math_primary_agent",
                    "provenance": {"review_type": "AI only,not human/expert gold"},
                    "reviewed_at": "2026-11-15T10:01:00+07:00",
                    "supersedes_receipt_line_sha256_including_line_ending": _sha(main_line),
                }
                (judging / f"track_c_reviews_{category}_agent_v1_corrections.jsonl").write_bytes(_line(correction))
                schema_overlay = {
                    **identity, "schema_fields_added": ["correct_abstention", "false_refusal"],
                    "source_receipt_file": main_path.name,
                    "source_receipt_line_sha256_including_line_ending": _sha(main_line),
                    "correct_abstention": None, "false_refusal": None,
                }
                (judging / f"track_c_reviews_{category}_agent_v1_schema_overlay.jsonl").write_bytes(
                    _line(schema_overlay))
            else:
                main_path.write_bytes(b"")

        source_manifest = {
            "schema_version": "track_c_blind_review_packets_v1",
            "prediction_history_sha256": _sha(prediction_line),
            "reviewer_protocol_sha256": "protocol-hash",
            "effective_latest_cases": 1,
            "categories": category_meta,
        }
        (judging / "blind_review_manifest_v1.json").write_text(
            json.dumps(source_manifest), encoding="utf-8")
        return run_dir, rid

    def test_correction_and_null_schema_overlays_are_applied(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, rid = self._fixture(Path(tmp))
            result = consolidate(run_dir)
            output = run_dir / "judging" / "effective_reviews_ai_v1.jsonl"
            effective = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(effective["review_id"], rid)
            self.assertEqual(effective["correctness"], 0.5)
            self.assertIsNone(effective["correct_abstention"])
            self.assertIsNone(effective["false_refusal"])
            self.assertEqual(result["overlay_counts"], {"corrections": 1, "schema_defaults": 2})
            self.assertEqual(result["effective_review_count"], 1)

    def test_wrong_superseded_line_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ = self._fixture(Path(tmp))
            path = run_dir / "judging" / "track_c_reviews_math_agent_v1_corrections.jsonl"
            row = json.loads(path.read_text(encoding="utf-8"))
            row["supersedes_receipt_line_sha256_including_line_ending"] = "wrong-hash"
            path.write_bytes(_line(row))
            with self.assertRaisesRegex(ValueError, "superseded source hash mismatch"):
                consolidate(run_dir)

    def test_protocol_field_overlay_fills_missing_category_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, rid = self._fixture(Path(tmp))
            judging = run_dir / "judging"
            main_path = judging / "track_c_reviews_math_agent_v1.jsonl"
            main = json.loads(main_path.read_text(encoding="utf-8"))
            for field in ("algorithm_reasoning", "formula_fidelity", "numeric_protocol_accuracy"):
                main.pop(field)
            main_line = _line(main)
            main_path.write_bytes(main_line)

            correction = judging / "track_c_reviews_math_agent_v1_corrections.jsonl"
            correction.unlink()
            schema_path = judging / "track_c_reviews_math_agent_v1_schema_overlay.jsonl"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["source_receipt_line_sha256_including_line_ending"] = _sha(main_line)
            schema_path.write_bytes(_line(schema))

            overlay = {
                "review_id": rid, "question_id": "math-0001", "source_file": main_path.name,
                "source_line_number": 1,
                "source_line_sha256_including_line_ending": _sha(main_line),
                "input_sha256": "input-hash", "packet_sha256": "packet-hash",
                "evidence_sha256": "evidence-hash",
                "source_prediction_line_sha256_including_line_ending": main["source_prediction_line_sha256_including_line_ending"],
                "algorithm_reasoning": True,
                "algorithm_reasoning_rationale": "The answer preserves the required step order.",
                "formula_fidelity": None,
                "formula_fidelity_rationale": "Not applicable to this item.",
                "numeric_protocol_accuracy": None,
                "numeric_protocol_accuracy_rationale": "No numeric protocol is tested.",
                "reviewer": "judge_primary_agent",
                "review_type": "AI-only protocol field overlay",
                "provenance": {"review_type": "AI-only; not human/expert gold"},
                "reviewed_at": "2026-11-15T10:02:00+07:00",
            }
            (judging / "track_c_reviews_math_agent_v1_protocol_fields_overlay_v1.jsonl").write_bytes(
                _line(overlay))

            result = consolidate(run_dir)
            effective = json.loads((judging / "effective_reviews_ai_v1.jsonl").read_text(encoding="utf-8"))
            self.assertTrue(effective["algorithm_reasoning"])
            self.assertIsNone(effective["formula_fidelity"])
            self.assertIsNone(effective["numeric_protocol_accuracy"])
            self.assertEqual(result["protocol_field_overlay_receipts"], 1)


if __name__ == "__main__":
    unittest.main()
