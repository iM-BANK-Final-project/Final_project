from pathlib import Path
import unittest


class FrontendCopyTests(unittest.TestCase):
    def test_active_frontend_uses_financial_dormancy_terms(self):
        source_paths = list(Path("src/frontend/rm-insight-copilot/src").rglob("*.jsx"))
        active_text = "\n".join(path.read_text(encoding="utf-8") for path in source_paths)

        self.assertNotIn("이탈잠재예측", active_text)
        self.assertNotIn("이탈 잠재위험", active_text)
        self.assertNotIn("급감·침묵", active_text)
        self.assertIn("금융관계 휴면화 예측", active_text)
        self.assertIn("금융관계 약화 위험", active_text)


if __name__ == "__main__":
    unittest.main()
