# Gemini AI Strategy Report and PDF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the AI report button to Gemini, render a validated six-section Korean strategy report, and download the same report as an in-memory Korean PDF.

**Architecture:** FastAPI builds the report evidence from the existing eligible-customer repository and injects only that evidence into a structured Gemini call. The backend combines Gemini's narrative with authoritative metrics and SHAP factors into one validated envelope; React renders that envelope and posts it back to a separate PDF endpoint that revalidates it against the database before rendering.

**Tech Stack:** Python 3.10, FastAPI, Pydantic, Google Gen AI SDK, ReportLab, pypdf tests, SQLite, React 19, Vitest, Testing Library.

## Global Constraints

- Generated reports and PDFs are not persisted to the database or filesystem.
- Only customers in the existing 3,341-row service database can be generated.
- Gemini credentials remain backend-only and are read through the existing `GEMINI_API_KEY`/Vertex AI configuration.
- Risk means the probability of `Y_INTERVENE_M12_v2` persistent transaction weakening in the next six months, not default, cancellation, or confirmed dormancy.
- CLV_Risk and PotentialLoss are scenario estimates, not confirmed losses.
- SHAP values are model contributions, not causal effects.
- Gemini writes only the six narrative sections; metrics and SHAP Top 10 are copied from the database by the backend.
- PDF is A4 portrait, embeds a Korean font, contains page numbers, and is created in memory.
- Production code follows red-green-refactor: every behavior is preceded by a failing test.

---

### Task 1: Structured AI report contracts

**Files:**
- Modify: `src/backend/schemas.py`
- Create: `tests/test_ai_report_schemas.py`
- Modify: `environment.yml`

**Interfaces:**
- Produces: `ReportMetrics`, `GeminiNarrative`, `GeneratedReport`, and bounded narrative/list fields for the Gemini and PDF layers.
- Consumes: existing `ShapFactor` and `Report` response models.

- [ ] **Step 1: Write failing schema tests**

Create tests that instantiate a valid report and assert rejection of an empty section, more than eight actions, more than six caveats, a malformed month, and more than ten SHAP factors:

```python
from pydantic import ValidationError
import pytest

from src.backend.schemas import GeneratedReport


def valid_payload():
    return {
        "corporateId": "A",
        "customerName": "에이기업",
        "asOfMonth": "2025-12",
        "generatedAt": "2026-07-21T13:00:00+09:00",
        "metrics": {"risk": 80.0, "clvRisk": 70.0, "potentialLoss": 30.0},
        "shapFactors": [
            {"feature": f"feature_{i}", "featureValue": None, "impact": 0.1, "rank": i}
            for i in range(1, 11)
        ],
        "riskSummary": "지속거래약화 가능성이 높아 조기 점검이 필요합니다.",
        "valueAssessment": "위험 반영 고객가치와 잠재손실 시나리오를 함께 봅니다.",
        "weakeningDrivers": "SHAP 기여도를 기준으로 주요 변화를 확인합니다.",
        "contactStrategy": "RM이 거래 변화의 배경을 우선 확인합니다.",
        "recommendedActions": ["접촉 일정 수립"],
        "caveats": ["확정 손실액이 아닙니다."],
    }


def test_generated_report_accepts_bounded_complete_payload():
    assert GeneratedReport.model_validate(valid_payload()).corporateId == "A"


@pytest.mark.parametrize("mutation", ["empty_summary", "too_many_actions", "too_many_shap", "bad_month"])
def test_generated_report_rejects_invalid_payload(mutation):
    payload = valid_payload()
    if mutation == "empty_summary":
        payload["riskSummary"] = " "
    elif mutation == "too_many_actions":
        payload["recommendedActions"] = ["조치"] * 9
    elif mutation == "too_many_shap":
        payload["shapFactors"].append(payload["shapFactors"][-1] | {"rank": 11})
    else:
        payload["asOfMonth"] = "202512"
    with pytest.raises(ValidationError):
        GeneratedReport.model_validate(payload)
```

- [ ] **Step 2: Run the schema tests and confirm RED**

Run: `conda run -n final python -m pytest tests/test_ai_report_schemas.py -q`

Expected: collection fails because `GeneratedReport` does not exist.

- [ ] **Step 3: Add bounded Pydantic models**

Add models with `StringConstraints(strip_whitespace=True, min_length=1, max_length=...)`, `conlist`, a `YYYY-MM` pattern, `risk` constrained to `0..100`, finite numeric fields, exactly one rank per supplied SHAP factor, and a maximum of ten factors. `GeminiNarrative` contains only the six narrative fields; `GeneratedReport` extends those fields with authoritative metadata, metrics, and SHAP factors.

- [ ] **Step 4: Declare runtime/test dependencies**

Add these pip dependencies to `environment.yml`:

```yaml
      - google-genai>=1.0,<2
      - reportlab>=4.2,<5
      - pypdf>=5,<6
```

- [ ] **Step 5: Run schema and existing schema tests**

Run: `conda run -n final python -m pytest tests/test_ai_report_schemas.py tests/test_service_api.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add environment.yml src/backend/schemas.py tests/test_ai_report_schemas.py
git commit -m "feat: define generated AI report contract"
```

### Task 2: Evidence-grounded Gemini generation service

**Files:**
- Modify: `src/backend/gemini_service.py`
- Create: `tests/test_gemini_service.py`

**Interfaces:**
- Consumes: `Report`-compatible dictionary returned by `ServiceRepository.report()`.
- Produces: `generate_strategy_report(context: dict) -> GeminiNarrative`.
- Raises: `ReportGenerationError` with a safe public message while preserving the original exception only as the exception cause.

- [ ] **Step 1: Write failing prompt and response tests**

Use a fake client whose `models.generate_content` captures `model`, `contents`, and config. Assert that the prompt contains the customer metrics, all ten SHAP factors, the stored recommendation, and the non-causal/non-confirmed-loss rules. Return a fake `response.parsed` narrative and assert `GeminiNarrative` is returned. Add tests for an empty response, invalid parsed response, client failure, and Vertex-to-API-key fallback.

```python
def test_generate_strategy_report_uses_only_evidence_and_validates_narrative():
    captured = {}
    narrative = {
        "riskSummary": "조기 점검이 필요합니다.",
        "valueAssessment": "확정 손실이 아닌 시나리오입니다.",
        "weakeningDrivers": "SHAP 예측 기여도를 확인합니다.",
        "contactStrategy": "RM 확인이 필요합니다.",
        "recommendedActions": ["접촉 일정 수립"],
        "caveats": ["해지 확률이 아닙니다."],
    }
    result = generate_strategy_report(report_context(), client=fake_client(captured, narrative))
    assert result.riskSummary == narrative["riskSummary"]
    assert "SHAP은 인과관계가 아닙니다" in captured["contents"]
    assert "feature_10" in captured["contents"]
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `conda run -n final python -m pytest tests/test_gemini_service.py -q`

Expected: import fails because `generate_strategy_report` and `ReportGenerationError` do not exist.

- [ ] **Step 3: Implement the dedicated Gemini service**

Keep `ask_gemini` compatible, but add:

```python
class ReportGenerationError(RuntimeError):
    pass


def generate_strategy_report(context: dict, client=None) -> GeminiNarrative:
    prompt = build_strategy_report_prompt(context)
    active_client = client or _make_client()
    response = active_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiNarrative,
            temperature=0.2,
        ),
    )
    payload = getattr(response, "parsed", None)
    if payload is None:
        payload = json.loads(response.text)
    return GeminiNarrative.model_validate(payload)
```

Serialize context with `json.dumps(..., ensure_ascii=False, allow_nan=False)`. Catch SDK, JSON, and validation errors at the public boundary and raise `ReportGenerationError("AI 보고서 생성에 실패했습니다.")`.

- [ ] **Step 4: Run focused tests**

Run: `conda run -n final python -m pytest tests/test_gemini_service.py -q`

Expected: all tests pass without a real Gemini request.

- [ ] **Step 5: Commit**

```bash
git add src/backend/gemini_service.py tests/test_gemini_service.py
git commit -m "feat: generate grounded Gemini strategy narratives"
```

### Task 3: In-memory Korean PDF renderer

**Files:**
- Create: `src/backend/report_pdf.py`
- Create: `tests/test_report_pdf.py`

**Interfaces:**
- Consumes: `render_strategy_report_pdf(report: GeneratedReport, font_path: Path | None = None) -> bytes`.
- Produces: PDF bytes beginning with `%PDF-`, with authoritative metrics, six narrative sections, SHAP Top 10, disclaimers, and page numbers.

- [ ] **Step 1: Read the PDF skill before PDF implementation**

Read `/Users/gggyyu/.codex/skills/pdf/SKILL.md` completely and follow its font, rendering, extraction, and visual-verification instructions.

- [ ] **Step 2: Write failing PDF tests**

Test the PDF signature and extract text with `pypdf.PdfReader(BytesIO(pdf_bytes))`. Assert the extracted text includes the corporate ID, month, section titles, metrics, `feature_10`, and disclaimers. Add a test that an unavailable explicit font raises a safe `PdfGenerationError`.

```python
def test_pdf_contains_same_report_sections_and_top10():
    pdf = render_strategy_report_pdf(generated_report(), font_path=korean_font())
    assert pdf.startswith(b"%PDF-")
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "에이기업" in text
    assert "주요 SHAP Value (상위 10개)" in text
    assert "feature_10" in text
```

- [ ] **Step 3: Run tests and confirm RED**

Run: `conda run -n final python -m pytest tests/test_report_pdf.py -q`

Expected: import fails because `report_pdf.py` does not exist.

- [ ] **Step 4: Implement ReportLab renderer**

Resolve `RM_REPORT_FONT_PATH` first, then common Korean font candidates including `/System/Library/Fonts/Supplemental/AppleGothic.ttf` and Linux Noto Sans CJK paths. Register the font with `pdfmetrics.registerFont(TTFont(...))`; use `SimpleDocTemplate(BytesIO(), pagesize=A4)`, `Paragraph`, `Table`, and a page callback for page numbers. Escape all dynamic text before making paragraphs. Do not write temporary files.

- [ ] **Step 5: Render and visually inspect the PDF**

Run focused tests, render a sample PDF to `outputs/rm_service/ai_report_sample.pdf` only as a manual verification artifact, convert its pages to PNG using the PDF skill's prescribed script, and inspect every page for Korean glyphs, clipping, table overflow, and page-number placement. Remove only temporary render PNGs created by this task; leave the sample under ignored `outputs/`.

- [ ] **Step 6: Commit**

```bash
git add src/backend/report_pdf.py tests/test_report_pdf.py
git commit -m "feat: render Korean AI strategy report PDFs"
```

### Task 4: FastAPI generation and PDF endpoints

**Files:**
- Modify: `src/backend/app.py`
- Modify: `tests/test_service_api.py`

**Interfaces:**
- Consumes: `generate_strategy_report(context) -> GeminiNarrative` and `render_strategy_report_pdf(report) -> bytes`.
- Produces: `POST /api/reports/{corporate_id}/generate` and `POST /api/reports/{corporate_id}/pdf`.
- `create_app` accepts optional `report_generator` and `pdf_renderer` callables for deterministic tests.

- [ ] **Step 1: Write failing endpoint tests**

Create an app with injected fake generator and renderer. Assert:

```python
response = client.post("/api/reports/A/generate", params={"as_of_month": "2025-12"})
assert response.status_code == 200
assert response.json()["metrics"] == {
    "risk": 80.0,
    "clvRisk": 70.0,
    "potentialLoss": 30.0,
}
assert len(response.json()["shapFactors"]) == 10

pdf_response = client.post("/api/reports/A/pdf", json=response.json())
assert pdf_response.status_code == 200
assert pdf_response.headers["content-type"] == "application/pdf"
assert pdf_response.content.startswith(b"%PDF-")
```

Add cases for unknown customer 404, generator error 502 with redacted detail, invalid body 422, customer/month/metric mismatch 400, and PDF renderer error 500 with a safe detail. Assert CORS preflight permits POST.

- [ ] **Step 2: Run tests and confirm RED**

Run: `conda run -n final python -m pytest tests/test_service_api.py -q`

Expected: POST endpoints return 405.

- [ ] **Step 3: Implement endpoint composition**

Extend `create_app` with optional callables, allow `GET` and `POST` in CORS, add a helper that combines authoritative customer metrics/SHAP with the narrative and current timezone-aware ISO timestamp, and return `Response(pdf_bytes, media_type="application/pdf", headers={...})`. Before PDF rendering, compare corporate ID, customer name, month, metrics, and SHAP factors with a fresh repository report.

- [ ] **Step 4: Run focused API tests**

Run: `conda run -n final python -m pytest tests/test_service_api.py tests/test_gemini_service.py tests/test_report_pdf.py -q`

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/backend/app.py tests/test_service_api.py
git commit -m "feat: expose AI report generation and PDF APIs"
```

### Task 5: React generation, rendering, and download flow

**Files:**
- Modify: `src/frontend/rm-insight-copilot/src/api/client.js`
- Create: `src/frontend/rm-insight-copilot/src/api/client.test.js`
- Modify: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/pages/AiReportPage.test.jsx`
- Modify: `src/frontend/rm-insight-copilot/src/styles.css`

**Interfaces:**
- Produces: `apiPost(path, body, params, signal) -> Promise<object>` and `apiPostBlob(path, body, params, signal) -> Promise<{blob, filename}>`.
- Consumes: the generated report envelope from Task 4.

- [ ] **Step 1: Write failing API-client tests**

Assert POST URL/query construction, JSON headers/body, safe API error extraction, blob return, RFC 5987 `filename*` decoding, plain `filename` fallback, and default filename.

- [ ] **Step 2: Run API-client tests and confirm RED**

Run: `npm test -- --run src/api/client.test.js`

Expected: named exports `apiPost` and `apiPostBlob` are missing.

- [ ] **Step 3: Implement POST helpers**

Factor common JSON error parsing without changing `apiGet`. For blob errors, inspect JSON only when the response content type is JSON. Return the response blob and a sanitized server-provided filename.

- [ ] **Step 4: Write failing AI-report UI tests**

Add tests that click `전략 보고서 생성`, verify the disabled `보고서 생성 중...` state, resolve the request, and assert all six section titles and `PDF 다운로드`. Add generation failure/retry, PDF blob download/URL revocation, PDF failure without report removal, and selected-customer change reset tests.

- [ ] **Step 5: Run UI tests and confirm RED**

Run: `npm test -- --run src/pages/AiReportPage.test.jsx`

Expected: the generation button does not call POST and no generated sections appear.

- [ ] **Step 6: Implement the UI state machine**

Maintain `generatedReport`, `generating`, `generationError`, `downloading`, and `downloadError` inside `StoredReport`. Reset them in an effect keyed by `selectedId` and `asOfMonth`. Render fixed semantic sections from the validated response. Use an object URL and temporary anchor for download and always call `URL.revokeObjectURL`.

- [ ] **Step 7: Style generated report and responsive controls**

Add focused classes for the generated report grid, numbered action list, caveat panel, error messages, and download button. Preserve the existing SHAP Top 10 layout and mobile breakpoint behavior.

- [ ] **Step 8: Run frontend tests and build**

Run: `npm test -- --run`

Expected: all tests pass.

Run: `npm run build`

Expected: Vite production build succeeds.

- [ ] **Step 9: Commit**

```bash
git add src/frontend/rm-insight-copilot/src/api/client.js src/frontend/rm-insight-copilot/src/api/client.test.js src/frontend/rm-insight-copilot/src/pages/AiReportPage.jsx src/frontend/rm-insight-copilot/src/pages/AiReportPage.test.jsx src/frontend/rm-insight-copilot/src/styles.css
git commit -m "feat: generate and download AI strategy reports"
```

### Task 6: Documentation, real integration check, and final verification

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `src/models/model.md`
- Modify: `tests/test_persistent_target_documentation.py`

**Interfaces:**
- Documents: environment setup, generation/PDF endpoints, non-persistence, report safety language, and Korean font configuration.

- [ ] **Step 1: Write failing documentation contract**

Require active documents to mention `POST /api/reports/{corporate_id}/generate`, `POST /api/reports/{corporate_id}/pdf`, `GEMINI_API_KEY`, `RM_REPORT_FONT_PATH`, and that reports are not persisted.

- [ ] **Step 2: Run documentation test and confirm RED**

Run: `conda run -n final python -m pytest tests/test_persistent_target_documentation.py -q`

Expected: fails because active docs do not yet describe the generation flow.

- [ ] **Step 3: Update active documentation**

Add exact startup/configuration examples without including secret values. State that automated tests mock Gemini and that PDF generation requires a readable Korean TrueType font through the environment variable or supported system fallback.

- [ ] **Step 4: Run one real Gemini integration request**

Use the existing `.env` and the default service database to call the generation function for one eligible customer. Print only the corporate ID, returned section names, and validation success; never print the API key. Then render the returned envelope to PDF and visually verify it using the PDF skill workflow.

- [ ] **Step 5: Run full verification**

Run: `conda run -n final python -m pytest -q`

Run: `npm test -- --run` from `src/frontend/rm-insight-copilot`.

Run: `npm run build` from `src/frontend/rm-insight-copilot`.

Run: `git diff --check`.

Expected: every command exits 0, Gemini returns a schema-valid Korean narrative, and the rendered PDF has no clipped or missing Korean text.

- [ ] **Step 6: Commit**

```bash
git add README.md AGENTS.md src/models/model.md tests/test_persistent_target_documentation.py
git commit -m "docs: document Gemini AI report generation"
```
