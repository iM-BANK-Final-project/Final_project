import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE_DOCS = [
    ROOT / "financial_dormancy.md",
    ROOT / "README.md",
    ROOT / "AGENTS.md",
    ROOT / "src/models/model.md",
]


class PersistentTargetDocumentationTest(unittest.TestCase):
    def test_active_docs_name_the_new_final_target(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Y_지속거래약화_3M70", text, path)

    def test_active_docs_do_not_present_old_target_as_current(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "모델 학습용 y는 `Y_핵심관계약화_3개월`",
                text,
                path,
            )

    def test_active_docs_do_not_claim_stale_performance(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("0.2959", text, path)
            self.assertNotIn("75.5%", text, path)


if __name__ == "__main__":
    unittest.main()
