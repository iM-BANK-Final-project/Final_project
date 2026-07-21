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
