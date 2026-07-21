import json
from pathlib import Path


NOTEBOOK = Path("src/models/web_202512_m12_final_model.ipynb")
PROFITABILITY_NOTEBOOK = Path("src/수익성F(y선정포함).ipynb")


def notebook_code() -> str:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in payload["cells"]
        if cell.get("cell_type") == "code"
    )


def code_from(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return "\n".join(
        "".join(cell.get("source", []))
        for cell in payload["cells"]
        if cell.get("cell_type") == "code"
    )


def test_final_web_notebook_exports_local_shap_top10():
    source = notebook_code()

    assert "add_local_shap_top10" in source
    assert "[:, :10]" in source
    assert "range(10)" in source
    assert "add_local_shap_top3" not in source


def test_final_notebooks_share_repository_paths_and_top10_contract():
    web_source = code_from(NOTEBOOK)
    profitability_source = code_from(PROFITABILITY_NOTEBOOK)

    assert "model_m12_intervene_v2_feature_registry.csv" in web_source
    assert "model_m12_intervene_v2_feature_sets.csv" not in web_source
    assert "[:, :10]" in profitability_source
    assert "range(10)" in profitability_source
    assert "/Users/changeun_1/" not in profitability_source


def test_web_notebook_exports_the_approved_eligible_operating_population():
    source = code_from(NOTEBOOK)

    assert "EXPECTED_SCORING_FIRMS = 3341" in source
    assert "web_m12_intervene_v2_scores_202512_eligible_3341.csv" in source
    assert "result['score_eligible'] = True" in source
    assert "risk_rank_eligible_3341" in source
    assert "risk_rank_all_3372" not in source


def test_profitability_notebook_accepts_repository_ftp_schema():
    source = code_from(PROFITABILITY_NOTEBOOK)

    assert "monthly_recombined_ytd_rate_decimal" in source
    assert "FTP 필수 컬럼을 찾을 수 없습니다." in source


def test_profitability_notebook_validates_annualized_corporate_loan_rate_range():
    source = code_from(PROFITABILITY_NOTEBOOK)

    assert "['기업대출금리_월_decimal'].between(0.02, 0.10)" in source
    assert "['기업대출금리_월_decimal'].between(0.002, 0.01)" not in source
