"""FastAPI application exposing stored RM insight results."""

import logging
import os
from pathlib import Path
import sqlite3
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.backend.database import connect_database
from src.backend.repository import DatabaseUnavailable, ServiceRepository
from src.backend.schemas import (
    Customer,
    CustomerPage,
    FilterOptions,
    Health,
    Overview,
    RecommendationPage,
    Report,
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


def create_app(repository: ServiceRepository | None = None) -> FastAPI:
    application = FastAPI(title="RM Insight Service")
    application.state.repository = repository or _default_repository()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["GET"],
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
            "priority_rank", "risk", "value_proxy", "priority_score", "name"
        ] = "priority_rank",
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
            "crm_priority_rank", "risk", "value_proxy", "priority_score", "name"
        ] = "crm_priority_rank",
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

    return application


app = create_app()
