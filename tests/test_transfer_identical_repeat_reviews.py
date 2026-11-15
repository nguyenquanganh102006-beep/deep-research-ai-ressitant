import json
import tempfile
import unittest
from pathlib import Path

from scripts.transfer_identical_repeat_reviews import transfer
from src.benchmark.scoring_local import review_id


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


class TransferRepeatReviewTests(unittest.TestCase):
    def _fixture(self, root: Path):
        baseline, repeat = root / "baseline", root / "repeat"
        baseline.mkdir(); repeat.mkdir()
        protocol = {"seed": 42, "temperature": 0.1, "num_ctx": 4096}
        for run, seed in ((baseline, 42), (repeat, 43)):
            manifest = {"git_sha": "commit", "prompt_sha256": "prompt", "packets_sha256": "packets",
                        "protocol": {**protocol, "seed": seed},
                        "models": [{"model_tag": "model", "model_digest": "digest", "quantization": "Q4_K_M"}]}
            (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        base_rows, repeat_rows, receipts, template = [], [], [], []
        for qid, answer42, answer43 in (("math-1", "same", "same"), ("code-1", "old", "new")):
            common = {"model_digest": "digest", "model_tag": "model", "quantization": "Q4_K_M",
                      "input_sha256": f"input-{qid}", "evidence_sha256": f"evidence-{qid}",
                      "prompt_sha256": "prompt", "track": "gold_text_verified", "status": "completed",
                      "question_id": qid}
            base = {**common, "run_id": "seed42", "answer": answer42}
            rep = {**common, "run_id": "seed43", "answer": answer43}
            base_rows.append(base); repeat_rows.append(rep)
            receipts.append({"review_id": review_id(base), "question_id": qid, "correctness": 1,
                             "citation_supported": True, "reviewer": "judge", "provenance": {"review_type": "AI only"}})
            template.append({"review_id": review_id(rep), "question_id": qid, "answer": answer43,
                             "reference_answer": "gold", "rubric": "rubric"})
        _write_jsonl(baseline / "predictions.jsonl", base_rows)
        _write_jsonl(repeat / "predictions.jsonl", repeat_rows)
        _write_jsonl(baseline / "reviews.jsonl", receipts)
        _write_jsonl(repeat / "review_template.jsonl", template)
        return baseline, baseline / "reviews.jsonl", repeat

    def test_transfers_only_identical_answers_and_queues_changed_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, reviews, repeat = self._fixture(Path(tmp))
            out = Path(tmp) / "transferred.jsonl"
            pending = Path(tmp) / "pending.jsonl"
            manifest = Path(tmp) / "manifest.json"
            result = transfer(baseline, reviews, repeat, out, pending, manifest)
            transferred = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
            queued = [json.loads(x) for x in pending.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(transferred), 1)
            self.assertEqual(transferred[0]["question_id"], "math-1")
            self.assertEqual(transferred[0]["provenance"]["transfer_source_seed"], 42)
            self.assertEqual(len(queued), 1)
            self.assertEqual(queued[0]["question_id"], "code-1")
            self.assertEqual(result["identical_answer_reviews_transferred"], 1)

    def test_rejects_changed_input_even_when_answer_is_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            baseline, reviews, repeat = self._fixture(Path(tmp))
            path = repeat / "predictions.jsonl"
            rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]
            rows[0]["input_sha256"] = "wrong"
            _write_jsonl(path, rows)
            with self.assertRaisesRegex(ValueError, "input/config mismatch"):
                transfer(baseline, reviews, repeat, Path(tmp)/"out.jsonl", Path(tmp)/"pending.jsonl",
                         Path(tmp)/"manifest.json")


if __name__ == "__main__":
    unittest.main()
