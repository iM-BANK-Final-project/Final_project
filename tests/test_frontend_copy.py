from pathlib import Path
import unittest


class FrontendCopyTests(unittest.TestCase):
    def test_active_frontend_uses_persistent_weakening_terms(self):
        source_root = Path("src/frontend/rm-insight-copilot/src")
        jsx_paths = list(source_root.rglob("*.jsx"))
        active_text = "\n".join(path.read_text(encoding="utf-8") for path in jsx_paths)

        self.assertNotIn("이탈잠재예측", active_text)
        self.assertNotIn("이탈 잠재위험", active_text)
        self.assertNotIn("급감·침묵", active_text)
        self.assertIn("지속거래약화 예측", active_text)
        self.assertIn("지속거래약화 위험", active_text)
        self.assertIn("CRM 우선순위 점수", active_text)
        self.assertNotIn("금융관계 휴면화 예측", active_text)
        self.assertNotIn("휴면위험", active_text)
        self.assertNotIn("기대손실", active_text)

    def test_active_frontend_does_not_import_mock_data(self):
        source_root = Path("src/frontend/rm-insight-copilot/src")
        source_paths = [
            *source_root.rglob("*.js"),
            *source_root.rglob("*.jsx"),
        ]

        for path in source_paths:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("data/mockData", source, msg=f"active mock import in {path}")


if __name__ == "__main__":
    unittest.main()
