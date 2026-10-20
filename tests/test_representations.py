"""Regression checks for loss-aware math/code indexing fields."""

import unittest

from src.representations import build_representations, looks_like_math


class RepresentationTests(unittest.TestCase):
    def test_raw_formula_is_preserved_and_symbols_are_searchable(self) -> None:
        formula = "β₁ = 0.9; θₜ = θₜ₋₁ − α · gₜ"
        representation = build_representations(formula, "math")

        self.assertEqual(representation["raw_text"], formula)
        self.assertEqual(representation["latex_status"], "heuristic_unverified")
        candidate = representation["latex_candidate"]
        self.assertIn(r"\beta_{1}", candidate)
        self.assertIn(r"\theta_{t-1}", candidate)
        self.assertIn(r"\alpha", candidate)

    def test_square_root_groups_its_argument(self) -> None:
        representation = build_representations("√(vₜ) + ε", "math")
        self.assertIn(r"\sqrt{v_{t}}", representation["latex_candidate"])

    def test_layout_damaged_markdown_does_not_get_a_fake_formula(self) -> None:
        damaged = "_θ_ - _t_ _←_ _θt−_ 1 _−_ _α ·_ _mt/_ ( _[√]_ _vt_ + _ϵ_ )"
        representation = build_representations(damaged, "mixed")
        self.assertEqual(representation["raw_text"], damaged)
        self.assertIsNone(representation["latex_candidate"])

    def test_ascii_equation_is_detected_as_math(self) -> None:
        self.assertTrue(looks_like_math("B_c = ceil(M/(4*d))"))

    def test_algorithm_is_kept_verbatim_as_pseudocode(self) -> None:
        code = "Algorithm 1\nRequire: α, β₁\n1: m ← 0\n2: while θ not converged do"
        representation = build_representations(code, "code")
        self.assertEqual(representation["code_text"], code)
        self.assertEqual(representation["code_kind"], "pseudocode")

    def test_mixed_prose_and_math_is_not_mislabeled_as_code(self) -> None:
        representation = build_representations(
            "The update is β₁ = 0.9, as shown in the equation.", "mixed"
        )
        self.assertIsNone(representation["code_text"])


if __name__ == "__main__":
    unittest.main()
