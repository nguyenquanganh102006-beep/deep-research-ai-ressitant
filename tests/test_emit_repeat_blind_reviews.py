import json
import tempfile
import unittest
from pathlib import Path

from scripts.emit_repeat_blind_reviews import emit


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class EmitRepeatBlindReviewsTests(unittest.TestCase):
    def test_appends_blind_receipt_with_source_hashes_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = {"review_id": "opaque", "question_id": "negative-1", "category": "unanswerable",
                      "model_answer": "No count is given. [Trang 2]", "allowed_pages": [2],
                      "input_sha256": "input", "evidence_sha256": "evidence", "packet_sha256": "packet",
                      "source_prediction_line_sha256_including_line_ending": "line", "output_truncated": False}
            packet_path, protocol_path, output = root / "packet.jsonl", root / "protocol.json", root / "out.jsonl"
            _write_jsonl(packet_path, [packet])
            protocol_path.write_text("{}", encoding="utf-8")
            decision = {"correctness": 1, "citation_supported": True, "primary_error": None,
                        "notes": "Evidence does not state a count.",
                        "claims": [{"text": "No exact count is given.", "supported": True, "source": "evidence",
                                    "cited_pages": [2], "reason": "The evidence omits a count."}],
                        "formula_fidelity": None, "algorithm_reasoning": None,
                        "numeric_protocol_accuracy": True, "correct_abstention": True, "false_refusal": False}
            result = emit(packet_path, output, {"opaque": decision}, protocol_path, reviewed_at="2026-11-15T12:00:00+07:00")
            self.assertEqual(result["new_receipts"], 1)
            row = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(row["source_prediction_line_sha256_including_line_ending"], "line")
            self.assertEqual(row["provenance"]["review_type"], "AI only, not human/expert gold")
            again = emit(packet_path, output, {"opaque": decision}, protocol_path, reviewed_at="2026-11-15T12:00:00+07:00")
            self.assertEqual(again["new_receipts"], 0)

    def test_rejects_citation_outside_allowed_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            packet = {"review_id": "opaque", "question_id": "negative-1", "category": "unanswerable",
                      "model_answer": "See [Trang 3].", "allowed_pages": [2], "input_sha256": "input",
                      "evidence_sha256": "evidence", "packet_sha256": "packet",
                      "source_prediction_line_sha256_including_line_ending": "line"}
            packet_path, protocol_path = root / "packet.jsonl", root / "protocol.json"
            _write_jsonl(packet_path, [packet])
            protocol_path.write_text("{}", encoding="utf-8")
            decision = {"correctness": 0, "citation_supported": True, "notes": "Wrong page.",
                        "claims": [{"text": "Claim.", "supported": False, "source": "none",
                                    "cited_pages": [], "reason": "Page 3 is outside the packet."}]}
            with self.assertRaisesRegex(ValueError, "must be unsupported"):
                emit(packet_path, root / "out.jsonl", {"opaque": decision}, protocol_path)


if __name__ == "__main__":
    unittest.main()
