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


def test_shap_llm_guide_states_operational_limits_and_raw_top10_contract():
    text = Path("src/SHAP_LLM_REPORT_GUIDE.md").read_text(encoding="utf-8")

    assert "16개 기본 피처 + 40개 동적 피처" in text
    assert "선택된 Top 10" in text
    assert "전체 모델 피처의 기여 비중이나 확률 변화량이 아니다" in text
    assert "프롬프트는 값·금액·변화율을 추정하지 말라고 지시한다" in text
    assert "현재 후처리만으로 생성된 모든" in text
    assert "숫자가 근거에 기반했는지 완전히 검증하지 못한다" in text
    assert "RM 또는 원천 근거 확인이 필요하다" in text
    assert "`shapFactors`는 authoritative context에서 변경하지 않는다" in text
    assert "`localShapTop10`은 검증된 `rank` 오름차순으로 정렬한다" in text
    assert "모든 원본 필드를 보존" in text
    assert "저장된 원본 행을 모두 표시하며 운영 적격 고객은 통상 10개" in text
    assert "Y는 실제 해지·부도·확정 휴면이 아닌 지속거래약화 proxy 예측입니다." in text
    assert "SHAP은 인과관계나 확률 변화량이 아닌 모델 예측 기여도입니다." in text
    assert "CLV_Risk와 PotentialLoss는 확정 손실액이 아닌 시나리오 추정치입니다." in text
    assert "정량 %, %p, bp 또는 숫자-만큼" in text
    assert "일반적인 인과 표현은 프롬프트에서 금지하지만 후처리가 빠짐없이 탐지하지는 않는다" in text
    assert "특정 피처의 방향과 반대되는" in text
    assert "개별 해지 확률, 부도 확률, 휴면 확률 표현은" in text
    assert "해지·부도·휴면 확률이라는 표현은" not in text
    assert "문장 안의 downstream 부정 표현" not in text
    assert "부정 문맥이면 원문을 보존" not in text
    assert "Top 10 내부 절대 SHAP 비중은 허용" in text
    assert "위험·확률의 수치 변화나 결과값에 결합" in text
    assert "명시적으로 부정된 방향 표현은 방향 판정에서 제외" in text
    assert "직접 결합된 부정 predicate" in text
    assert "무관한 downstream 부정은 정규화를 막지 않는다" in text
    assert "허용된 Top 10 비중 span만 marker로 치환" in text
    assert "나머지 clause의 위험·확률 수치 결합 검사를 계속" in text
    assert "명시적 내부 분모" in text
    assert "일반적인 `Top 10 SHAP` 문구는 허용 span이 아니다" in text
    assert "변하다·변동하다·바뀌다·차지하다" in text
