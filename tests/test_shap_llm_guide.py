from pathlib import Path


def test_shap_llm_guide_matches_fs2_top10_contract():
    text = Path("src/SHAP_LLM_REPORT_GUIDE.md").read_text(encoding="utf-8")

    assert "FS2_R1_DACK_DYNAMIC" in text
    assert "총 56개" in text
    assert "Local SHAP Top 10" in text
    assert "Top 10 원본" in text
    assert "업종·지역·고객등급·전담여부는 모델 입력이 아니다" in text
    assert "FS1_CAT" not in text
    assert "89개" not in text
    assert "CAT_*" not in text
