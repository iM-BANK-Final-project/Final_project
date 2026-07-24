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
    def test_active_docs_name_the_final_operating_target(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("Y_INTERVENE_M12_v2", text, path)
            self.assertIn("3,341", text, path)
            self.assertIn("CLV_Risk", text, path)
            self.assertIn("PotentialLoss", text, path)

    def test_active_docs_do_not_present_retired_contracts_as_current(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(
                "모델 학습용 y는 `Y_핵심관계약화_3개월`",
                text,
                path,
            )
            self.assertNotIn("CRM 관리 우선순위 점수\n=", text, path)
            self.assertNotIn("고객가치 대리지표\n=", text, path)

    def test_active_docs_do_not_claim_stale_performance(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("0.2959", text, path)
            self.assertNotIn("75.5%", text, path)

    def test_active_docs_name_the_final_164_operating_artifacts(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                "web_m12_final_scores_202512_all_3372.csv",
                text,
                path,
            )
            self.assertIn(
                "web_m12_final_risk_trend_202507_202512.csv",
                text,
                path,
            )
            self.assertIn("FS_FINAL_164_TUNED", text, path)
            self.assertIn("Platt", text, path)
            self.assertIn("SHAP Top 10", text, path)

    def test_active_docs_describe_gemini_generation_and_ephemeral_pdf(self):
        for path in ACTIVE_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertIn("POST /api/reports/{corporate_id}/generate", text, path)
            self.assertIn("POST /api/reports/{corporate_id}/pdf", text, path)
            self.assertIn("GEMINI_API_KEY", text, path)
            self.assertIn("RM_REPORT_FONT_PATH", text, path)
            self.assertIn("DB에 저장하지 않", text, path)


if __name__ == "__main__":
    unittest.main()
