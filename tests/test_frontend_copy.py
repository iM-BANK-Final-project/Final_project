from pathlib import Path
import unittest


class FrontendCopyTests(unittest.TestCase):
    def test_active_frontend_uses_persistent_weakening_terms(self):
        source_root = Path("src/frontend/rm-insight-copilot/src")
        jsx_paths = [
            path for path in source_root.rglob("*.jsx")
            if not path.name.endswith(".test.jsx")
        ]
        active_text = "\n".join(path.read_text(encoding="utf-8") for path in jsx_paths)

        self.assertNotIn("이탈잠재예측", active_text)
        self.assertNotIn("이탈 잠재위험", active_text)
        self.assertNotIn("급감·침묵", active_text)
        self.assertIn("지속거래약화 예측", active_text)
        self.assertIn("지속거래약화 위험", active_text)
        self.assertIn("CLV_Risk", active_text)
        self.assertIn("PotentialLoss", active_text)
        self.assertIn("최근 6개월 실제 FISIM을 위험확률로 조정한", active_text)
        self.assertNotIn("FISIM 기반 향후 6개월 경제적 기여가치", active_text)
        self.assertIn("잠재손실 방어대상 합계", active_text)
        self.assertNotIn("고객가치 대리지표", active_text)
        self.assertNotIn("CRM 우선순위 점수", active_text)
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
