import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_repeat_blind_reviews import prepare
from src.benchmark.scoring_local import review_id


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


class PrepareRepeatBlindReviewsTests(unittest.TestCase):
    def _fixture(self, root: Path):
        run = root / "run"
        judging = run / "judging"
        judging.mkdir(parents=True)
        prediction = {
            "run_id": "seed43", "track": "gold_text_verified", "question_id": "negative-1",
            "model_tag": "private-model", "model_digest": "private-digest", "quantization": "Q4_K_M",
            "category": "unanswerable", "status": "completed", "answer": "Cannot tell from evidence.",
            "question": "How many?", "allowed_pages": [2], "input_sha256": "input-sha",
            "evidence_sha256": "evidence-sha", "packet_sha256": "packet-sha", "output_truncated": False,
        }
        packet = {
            "question_id": "negative-1", "category": "unanswerable", "question": "How many?",
            "evidence": [{"page_start": 2, "page_end": 2, "content": "No count is given."}],
            "evidence_sha256": "evidence-sha", "packet_sha256": "packet-sha",
        }
        template = {
            "review_id": review_id(prediction), "question_id": "negative-1", "category": "unanswerable",
            "question": "How many?", "answer": "Cannot tell from evidence.",
            "reference_answer": "The packet does not state a count.", "rubric": ["Do not invent a count."],
        }
        pending = {"review_id": review_id(prediction), "question_id": "negative-1",
                   "category": "unanswerable", "answer": "Cannot tell from evidence."}
        predictions = run / "predictions.jsonl"
        packet_path = root / "packets.jsonl"
        template_path = run / "review_template.jsonl"
        pending_path = judging / "pending.jsonl"
        _write_jsonl(predictions, [prediction])
        _write_jsonl(packet_path, [packet])
        _write_jsonl(template_path, [template])
        _write_jsonl(pending_path, [pending])
        return run, packet_path, pending_path, judging / "blind", pending["review_id"]

    def test_blind_packets_keep_evidence_hashes_and_omit_model_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, packet_path, pending_path, output, expected_id = self._fixture(Path(tmp))
            result = prepare(run, packet_path, pending_path, output, 7)
            blind = [json.loads(line) for line in (output / "blind_unanswerable_v1.jsonl").read_text(
                encoding="utf-8").splitlines()]
            self.assertEqual(result["blind_review_count"], 1)
            self.assertEqual(blind[0]["review_id"], expected_id)
            self.assertEqual(blind[0]["retrieved_evidence"][0]["page_start"], 2)
            self.assertEqual(blind[0]["source_prediction_line_sha256_including_line_ending"],
                             hashlib.sha256((run / "predictions.jsonl").read_bytes()).hexdigest())
            self.assertFalse({"model_tag", "model_digest", "track", "run_id"} & blind[0].keys())

    def test_rejects_pending_question_category_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            run, packet_path, pending_path, output, _ = self._fixture(Path(tmp))
            rows = [json.loads(line) for line in pending_path.read_text(encoding="utf-8").splitlines()]
            rows[0]["category"] = "code"
            _write_jsonl(pending_path, rows)
            with self.assertRaisesRegex(ValueError, "pending answer/category mismatch"):
                prepare(run, packet_path, pending_path, output, 7)


if __name__ == "__main__":
    unittest.main()
