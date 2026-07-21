"""FastAPI application exposing stored RM insight results."""

import logging
import os
from pathlib import Path
import sqlite3
from datetime import datetime
from typing import Annotated, Callable, Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from src.backend.database import connect_database
from src.backend.gemini_service import (
    ReportGenerationError,
    generate_strategy_report,
)
from src.backend.report_pdf import PdfGenerationError, render_strategy_report_pdf
from src.backend.repository import DatabaseUnavailable, ServiceRepository
from src.backend.schemas import (
    Customer,
    CustomerPage,
    FilterOptions,
    GeneratedReport,
    GeminiNarrative,
    Health,
    Overview,
    RecommendationPage,
    Report,
    ReportMetrics,
    ShapFactor,
)


LOGGER = logging.getLogger(__name__)
DEFAULT_DATABASE_PATH = Path("outputs/rm_service/rm_service.sqlite")
AsOfMonth = Annotated[
    str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
]


def _default_repository() -> ServiceRepository:
    path = Path(os.environ.get("RM_SERVICE_DB_PATH", DEFAULT_DATABASE_PATH))

    def connection_factory():
        if not path.is_file():
            raise FileNotFoundError(path)
        return connect_database(path)

    return ServiceRepository(connection_factory)


def create_app(
    repository: ServiceRepository | None = None,
    *,
    report_generator: Callable[[dict], GeminiNarrative] = generate_strategy_report,
    pdf_renderer: Callable[[GeneratedReport], bytes] = render_strategy_report_pdf,
) -> FastAPI:
    application = FastAPI(title="RM Insight Service")
    application.state.repository = repository or _default_repository()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def repo(request: Request) -> ServiceRepository:
        return request.app.state.repository

    @application.exception_handler(DatabaseUnavailable)
    async def unavailable_handler(_request: Request, _error: DatabaseUnavailable):
        return JSONResponse(
            status_code=503,
            content={"detail": "서비스 데이터베이스를 사용할 수 없습니다."},
        )

    @application.exception_handler(sqlite3.Error)
    async def sqlite_error_handler(_request: Request, error: sqlite3.Error):
        LOGGER.exception("RM service database query failed", exc_info=error)
        return JSONResponse(
            status_code=500, content={"detail": "데이터 조회 중 오류가 발생했습니다."}
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, error: Exception):
        LOGGER.error(
            "Unexpected RM service error",
            exc_info=(type(error), error, error.__traceback__),
        )
        return JSONResponse(
            status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."}
        )

    @application.get("/api/health", response_model=Health)
    def health(request: Request):
        repo(request).health()
        return {"status": "ok", "database": "available"}

    @application.get("/api/overview", response_model=Overview)
    def overview(request: Request, as_of_month: AsOfMonth = None):
        result = repo(request).overview(as_of_month)
        if result is None:
            raise HTTPException(status_code=404, detail="기준월을 찾을 수 없습니다.")
        return result

    @application.get("/api/filter-options", response_model=FilterOptions)
    def filter_options(request: Request, as_of_month: AsOfMonth = None):
        return repo(request).filter_options(as_of_month)

    @application.get("/api/customers", response_model=CustomerPage)
    def customers(
        request: Request,
        search: str | None = None,
        segment: str | None = None,
        risk_level: str | None = None,
        industry: str | None = None,
        region: str | None = None,
        dedicated: Literal["Y", "N"] | None = None,
        as_of_month: AsOfMonth = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        sort_by: Literal[
            "defense_rank", "risk", "clv_risk", "potential_loss", "name"
        ] = "defense_rank",
        sort_order: Literal["asc", "desc"] = "asc",
    ):
        return repo(request).customers(
            search=search,
            segment=segment,
            risk_level=risk_level,
            industry=industry,
            region=region,
            dedicated=dedicated,
            as_of_month=as_of_month,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @application.get("/api/customers/{corporate_id}", response_model=Customer)
    def customer_detail(
        corporate_id: str, request: Request, as_of_month: AsOfMonth = None
    ):
        result = repo(request).customer_detail(corporate_id, as_of_month)
        if result is None:
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다.")
        return result

    @application.get("/api/priorities", response_model=CustomerPage)
    def priorities(
        request: Request,
        industry: str | None = None,
        region: str | None = None,
        dedicated: Literal["Y", "N"] | None = None,
        weakening_type: str | None = None,
        segment: str | None = None,
        as_of_month: AsOfMonth = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        sort_by: Literal[
            "defense_rank", "risk", "clv_risk", "potential_loss", "name"
        ] = "defense_rank",
        sort_order: Literal["asc", "desc"] = "asc",
    ):
        return repo(request).priorities(
            industry=industry,
            region=region,
            dedicated=dedicated,
            weakening_type=weakening_type,
            segment=segment,
            as_of_month=as_of_month,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    @application.get("/api/recommendations", response_model=RecommendationPage)
    def recommendations(
        request: Request,
        segment: str | None = None,
        weakening_type: str | None = None,
        as_of_month: AsOfMonth = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ):
        return repo(request).recommendations(
            segment=segment,
            weakening_type=weakening_type,
            as_of_month=as_of_month,
            page=page,
            page_size=page_size,
        )

    @application.get("/api/reports/{corporate_id}", response_model=Report)
    def report(corporate_id: str, request: Request, as_of_month: AsOfMonth = None):
        result = repo(request).report(corporate_id, as_of_month)
        if result is None:
            raise HTTPException(status_code=404, detail="고객 보고서를 찾을 수 없습니다.")
        return result

    def report_context(
        corporate_id: str, request: Request, as_of_month: str | None
    ) -> tuple[dict, str]:
        active_repository = repo(request)
        resolved_month = as_of_month
        if resolved_month is None:
            resolved_month = active_repository.filter_options(None)["asOfMonth"]
        context = active_repository.report(corporate_id, resolved_month)
        if context is None:
            raise HTTPException(status_code=404, detail="고객 보고서를 찾을 수 없습니다.")
        return context, resolved_month

    def authoritative_report(
        context: dict, month: str, narrative: GeminiNarrative
    ) -> GeneratedReport:
        customer = context["customer"]
        return GeneratedReport(
            corporateId=customer["id"],
            customerName=customer["name"],
            asOfMonth=month,
            generatedAt=datetime.now(ZoneInfo("Asia/Seoul")),
            metrics=ReportMetrics(
                risk=customer["risk"],
                clvRisk=customer["clvRisk"],
                potentialLoss=customer["potentialLoss"],
            ),
            shapFactors=[ShapFactor.model_validate(item) for item in context["shapFactors"]],
            **narrative.model_dump(),
        )

    @application.post(
        "/api/reports/{corporate_id}/generate", response_model=GeneratedReport
    )
    def generate_report(
        corporate_id: str, request: Request, as_of_month: AsOfMonth = None
    ):
        context, resolved_month = report_context(corporate_id, request, as_of_month)
        try:
            narrative = report_generator(context)
        except ReportGenerationError as error:
            LOGGER.warning("Gemini strategy report generation failed", exc_info=error)
            raise HTTPException(
                status_code=502, detail="AI 보고서 생성에 실패했습니다."
            ) from error
        return authoritative_report(context, resolved_month, narrative)

    @application.post("/api/reports/{corporate_id}/pdf")
    def download_report_pdf(
        corporate_id: str, generated: GeneratedReport, request: Request
    ):
        context = repo(request).report(corporate_id, generated.asOfMonth)
        if context is None:
            raise HTTPException(
                status_code=400,
                detail="보고서 근거 데이터가 현재 고객 데이터와 다릅니다.",
            )
        customer = context["customer"]
        expected_metrics = ReportMetrics(
            risk=customer["risk"],
            clvRisk=customer["clvRisk"],
            potentialLoss=customer["potentialLoss"],
        )
        expected_factors = [
            ShapFactor.model_validate(item) for item in context["shapFactors"]
        ]
        evidence_matches = (
            generated.corporateId == corporate_id
            and generated.customerName == customer["name"]
            and generated.metrics == expected_metrics
            and generated.shapFactors == expected_factors
        )
        if not evidence_matches:
            raise HTTPException(
                status_code=400,
                detail="보고서 근거 데이터가 현재 고객 데이터와 다릅니다.",
            )
        try:
            pdf_bytes = pdf_renderer(generated)
        except PdfGenerationError as error:
            LOGGER.error("AI strategy report PDF rendering failed", exc_info=error)
            raise HTTPException(
                status_code=500, detail="PDF 보고서 생성에 실패했습니다."
            ) from error

        ascii_name = f"ai_strategy_report_{corporate_id}_{generated.asOfMonth}.pdf"
        korean_name = f"{generated.customerName}_AI_전략_보고서_{generated.asOfMonth}.pdf"
        disposition = (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(korean_name)}"
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": disposition},
        )

    return application


app = create_app()
