import json
from pathlib import Path


NOTEBOOK = Path("src/models/web_202512_m12_final_model.ipynb")


def notebook_code() -> str:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
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
