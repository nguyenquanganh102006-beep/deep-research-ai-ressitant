import json
import tempfile
import unittest
from pathlib import Path

from scripts.compare_repeat_seeds import compare_track
from src.benchmark.scoring_local import review_id


def _write_json(path: Path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


class CompareRepeatSeedsTests(unittest.TestCase):
    def _make_run(self, root: Path, seed: int, track="gold_text_verified", include_extra=False):
        run = root / f"seed{seed}"
        run.mkdir(parents=True)
        base_model = {"model_tag": "target", "model_digest": "digest-target", "quantization": "Q4_K_M"}
        models = [base_model]
        if include_extra:
            models.append({"model_tag": "other", "model_digest": "digest-other", "quantization": "Q4_K_M"})
        manifest = {"git_sha": "commit", "code_sha256": "code", "prompt_sha256": "prompt",
                    "packets_sha256": "packets", "track": track,
                    "protocol": {"seed": seed, "temperature": 0.1}, "models": models}
        _write_json(run / "manifest.json", manifest)
        predictions, reviews = [], []
        for model in models:
            pred = {"run_id": f"run-{seed}", "track": track, "question_id": "math-1",
                    "model_tag": model["model_tag"], "model_digest": model["model_digest"],
                    "quantization": model["quantization"], "input_sha256": "input", "evidence_sha256": "evidence",
                    "prompt_sha256": "prompt", "packet_sha256": "packets", "category": "math",
                    "status": "completed", "answer": "42"}
            predictions.append(pred)
            reviews.append({"review_id": review_id(pred), "question_id": "math-1", "correctness": 1,
                            "citation_supported": None, "reviewer": "judge",
                            "provenance": {"review_type": "AI only"}})
        _write_jsonl(run / "predictions.jsonl", predictions)
        review_path = run / "reviews.jsonl"
        _write_jsonl(review_path, reviews)
        return run, review_path

    def test_compares_only_models_present_in_all_three_seeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs, reviews = {}, {}
            for seed in (42, 43, 44):
                runs[seed], reviews[seed] = self._make_run(root, seed, include_extra=(seed == 42))
            report = compare_track("gold_text_verified", runs, reviews, expected_questions=1)
            self.assertEqual(len(report["models"]), 1)
            model = report["models"][0]
            self.assertEqual(model["model_tag"], "target")
            self.assertEqual(model["seed_metrics"]["44"]["all_eligible_mean_correctness"], 1.0)
            self.assertEqual(model["pairwise_exact_answer_repeat"]["42_vs_44"]["exact_answer_match_rate"], 1.0)

    def test_rejects_input_hash_mismatch_across_repeats(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs, reviews = {}, {}
            for seed in (42, 43, 44):
                runs[seed], reviews[seed] = self._make_run(root, seed)
            predictions_path = runs[43] / "predictions.jsonl"
            row = json.loads(predictions_path.read_text(encoding="utf-8"))
            row["input_sha256"] = "different"
            _write_jsonl(predictions_path, [row])
            with self.assertRaisesRegex(ValueError, "input_sha256 differs"):
                compare_track("gold_text_verified", runs, reviews, expected_questions=1)


if __name__ == "__main__":
    unittest.main()
