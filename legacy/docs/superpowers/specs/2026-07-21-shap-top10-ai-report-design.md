# AI Report SHAP Top 10 Design

## Purpose

Expand the saved AI report from three local SHAP factors to ten factors for every one of the 3,341 eligible operating customers. Display all ten factors at once and identify the section with a small title.

## Approved Model Rebuild

The original web pipeline that produced the retired Top 3 score artifact was unavailable. The user explicitly approved rebuilding the operating model from the final profitability notebook and recalculating risk, CLV, potential loss, and defense rank together. The active operating artifact is `src/models/web_m12_intervene_v2_scores_202512_eligible_3341.csv` and contains only the 3,341 eligible customers.

## Source and Ranking Contract

`src/models/web_202512_m12_final_model.ipynb` remains the source of truth for operating-score generation. Its local explanation step must calculate model contributions for all 56 features, exclude the LightGBM expected-value column, rank features by descending absolute contribution, and export ranks 1 through 10.

The operating score artifact must contain these pairs for every rank `n=1..10`:

```text
shap_top{n}_feature
shap_top{n}_value
```

Within one regenerated run, probability, SHAP, CLV, and defense priority must all derive from the same rebuilt model and calibrator.

## Service Data Contract

The service builder must require all ten feature/value pairs. For each eligible customer, it creates exactly ten `shap_factors` rows with `abs_shap_rank` 1 through 10.

Database preparation fails before replacing the existing SQLite database when:

- any Top 10 SHAP column is absent;
- a feature name or SHAP value is missing;
- a SHAP value is nonnumeric or non-finite;
- a customer does not produce exactly ten unique ranks.

For 3,341 eligible customers, the final database lock is 33,410 SHAP rows. SHAP factors remain stored results; the API and browser do not run the model.

## API Contract

The existing report endpoint continues returning `shapFactors`. It returns all stored factors ordered by `abs_shap_rank ASC`. Each eligible customer must receive ranks 1 through 10. No pagination or UI-specific truncation is added.

## UI Contract

The AI report page displays all ten returned factors at once using the existing SHAP marker and two-decimal contribution value format. It adds the small heading:

```text
주요 SHAP Value (상위 10개)
```

The heading appears immediately above the SHAP list. No collapse, “more” button, scroll-only viewport, or client-side slicing is used.

## Regeneration Path

The final score notebook is updated from Top 3 to Top 10. The operating score CSV must then be regenerated from the same locked model pipeline and operating feature set. After regeneration, run:

```bash
conda run -n final python -m src.backend.prepare_service_database
```

This rebuilds SQLite with exactly 3,341 customers and 33,410 SHAP rows.

If the locked model pipeline or operating feature artifact required to regenerate the score CSV is unavailable locally, implementation may complete the notebook and service contracts but must report artifact regeneration as an explicit remaining blocker rather than fabricate ranks 4 through 10.

## Testing

- Notebook-source contract test confirms Top 10 export logic and absence of a Top 3-only function.
- Service-builder test requires and expands all ten ranks.
- Database test verifies ten ranks per customer.
- API report test verifies ranks 1 through 10 in order.
- Frontend test verifies the small heading and ten visible factors without a “more” control.
- Full Python tests, frontend tests, production build, real database preparation, and SQLite row-count audit run before completion.

## Non-Goals

- Recomputing SHAP during an API request
- Changing the final model, probability calibration, features, or eligible population
- Showing global SHAP importance
- Adding chart interaction, pagination, or collapse behavior
