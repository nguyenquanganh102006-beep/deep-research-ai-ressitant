import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compare_track_c import compare
from src.benchmark.scoring_local import review_id


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CompareTrackCTests(unittest.TestCase):
    def _fixture(self, root: Path):
        vision_run, text_run = root / "vision", root / "text"
        vision_run.mkdir(); text_run.mkdir()
        (vision_run / "manifest.json").write_text(json.dumps({"prompt_sha256": "prompt", "git_sha": "c"}), encoding="utf-8")
        (text_run / "manifest.json").write_text(json.dumps({"prompt_sha256": "prompt", "git_sha": "b"}), encoding="utf-8")
        qids = ["math-1", "table-1"]
        vision_rows, text_rows = [], []
        for i, qid in enumerate(qids):
            category = "math" if i == 0 else "table"
            common = {"model_digest": "digest", "model_tag": "test", "quantization": "Q4_K_M",
                      "input_sha256": f"input-{qid}", "prompt_sha256": "prompt",
                      "evidence_sha256": f"evidence-{qid}", "category": category}
            vision_rows.append({**common, "evidence_sha256": f"vision-evidence-{qid}",
                                "run_id": "vision-run", "track": "retrieved_vision",
                                "question_id": qid, "answer": f"vision-{qid}", "status": "completed"})
            text_rows.append({**common, "run_id": "text-run", "track": "retrieved_text",
                              "question_id": qid, "answer": f"text-{qid}",
                              "status": "completed" if i == 0 else "resource_ineligible"})
        _write_jsonl(vision_run / "predictions.jsonl", vision_rows)
        _write_jsonl(text_run / "predictions.jsonl", text_rows)
        vision_reviews = root / "vision_reviews.jsonl"
        text_reviews = root / "text_reviews.jsonl"
        _write_jsonl(vision_reviews, [{"review_id": review_id(r), "correctness": 1.0 if i == 0 else 0.5}
                                      for i, r in enumerate(vision_rows)])
        _write_jsonl(text_reviews, [{"review_id": review_id(text_rows[0]), "correctness": 0.0}])
        vision_packets, text_packets = root / "vision_packets.jsonl", root / "text_packets.jsonl"
        tp = [{"question_id": qid, "evidence_sha256": f"evidence-{qid}", "evidence": [{"text": qid}],
              "category": "math" if i == 0 else "table"} for i, qid in enumerate(qids)]
        vp = [{**row, "source_evidence_sha256": row["evidence_sha256"],
               "evidence_sha256": f"vision-evidence-{row['question_id']}",
               "images": [{"sha256": f"image-{row['question_id']}"}]}
              for row in tp]
        _write_jsonl(vision_packets, vp); _write_jsonl(text_packets, tp)
        subset_manifest = root / "subset_manifest.json"
        subset_manifest.write_text(json.dumps({
            "vision_output": {"sha256": _sha(vision_packets)},
            "text_control_output": {"sha256": _sha(text_packets)},
            "paired_text_is_identical": True, "prompt_sha256": "prompt",
            "paired_prompt_sha256_by_question_id": {qid: f"input-{qid}" for qid in qids},
            "image_sha256_by_question_id": {qid: f"image-{qid}" for qid in qids},
        }), encoding="utf-8")
        return (vision_run, text_run, vision_reviews, text_reviews,
                vision_packets, text_packets, subset_manifest)

    def test_compares_exactly_paired_inputs_and_counts_failures_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = self._fixture(Path(tmp))
            result = compare(*args)
            stats = result["models"][0]["all_eligible"]
            self.assertEqual(stats["n"], 2)
            self.assertEqual(stats["mean_track_b"], 0.0)
            self.assertEqual(stats["mean_track_c"], 0.75)
            self.assertEqual(stats["wins_c"], 2)
            self.assertEqual(result["models"][0]["track_b_failures"], 1)
            self.assertEqual(result["models"][0]["both_completed"]["n"], 1)
            self.assertTrue(result["paired_input_hashes_match"])

    def test_rejects_input_mismatch_in_frozen_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = list(self._fixture(Path(tmp)))
            text_packets = args[5]
            rows = [json.loads(x) for x in text_packets.read_text(encoding="utf-8").splitlines()]
            rows[0]["evidence"][0]["text"] = "wrong"
            _write_jsonl(text_packets, rows)
            with self.assertRaisesRegex(ValueError, "packet hash does not match"):
                compare(*args)


if __name__ == "__main__":
    unittest.main()
