from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from src.backend.report_pdf import PdfGenerationError, render_strategy_report_pdf
from src.backend.schemas import GeneratedReport


KOREAN_FONT = Path("/System/Library/Fonts/Supplemental/AppleGothic.ttf")


def generated_report() -> GeneratedReport:
    return GeneratedReport.model_validate(
        {
            "corporateId": "A",
            "customerName": "에이기업",
            "asOfMonth": "2025-12",
            "generatedAt": "2026-07-21T13:00:00+09:00",
            "metrics": {"risk": 80.0, "clvRisk": 70.0, "potentialLoss": 30.0},
            "shapFactors": [
                {
                    "feature": f"feature_{rank}",
                    "featureValue": None,
                    "impact": (-1 if rank % 2 == 0 else 1) * rank / 100,
                    "rank": rank,
                }
                for rank in range(1, 11)
            ],
            "riskSummary": "지속거래약화 가능성이 높아 조기 점검이 필요합니다.",
            "valueAssessment": "CLV_Risk와 PotentialLoss는 확정 손실이 아닌 시나리오입니다.",
            "weakeningDrivers": "SHAP 예측 기여도를 기준으로 주요 변화를 확인합니다.",
            "contactStrategy": "RM이 거래 변화의 배경을 우선 확인합니다.",
            "recommendedActions": ["접촉 일정 수립", "거래 변화 사유 확인"],
            "caveats": [
                "실제 해지·부도·확정 휴면 확률이 아닙니다.",
                "SHAP은 인과관계가 아닌 모델 예측 기여도입니다.",
            ],
        }
    )


@pytest.mark.skipif(not KOREAN_FONT.is_file(), reason="macOS Korean font unavailable")
def test_pdf_contains_same_report_sections_and_top10():
    pdf = render_strategy_report_pdf(generated_report(), font_path=KOREAN_FONT)

    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    assert reader.pages
    page_texts = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(page_texts)
    assert "에이기업" in text
    assert "A" in text
    assert "2025-12" in text
    assert "종합 위험 요약" in text
    assert "고객가치 및 잠재손실 해석" in text
    assert "주요 SHAP Value (상위 10개)" in text
    assert "feature_10" in text
    assert "80.00%" in text
    assert "페이지 1" in text
    assert "&nbsp;" not in text
    assert len(page_texts) == 2
    assert "feature_1" in page_texts[1]
    assert "feature_10" in page_texts[1]


def test_pdf_rejects_unavailable_explicit_font():
    with pytest.raises(PdfGenerationError, match="한국어 폰트"):
        render_strategy_report_pdf(
            generated_report(), font_path=Path("/missing/korean-font.ttf")
        )
