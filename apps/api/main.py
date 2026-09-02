from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.middleware.request_context import RequestContextMiddleware
from apps.api.routers import API_V1_PREFIX
from apps.api.routers.admin_auth import router as admin_auth_router
from apps.api.routers.admin_sessions import router as admin_sessions_router
from apps.api.routers.admin_settings import router as admin_settings_router
from apps.api.routers.gateway import router as gateway_router
from apps.api.routers.gateway_rgb import router as gateway_rgb_router
from apps.api.routers.handwritten import router as handwritten_router
from apps.api.routers.health import router as health_router
from apps.api.routers.knowledge import router as knowledge_router
from src.pages_to_audio.common.errors import AppError
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    configure_logging(log_level=settings.LOG_LEVEL, service_name=settings.APP_NAME)
    logger.info("startup", app_env=settings.APP_ENV, app_name=settings.APP_NAME)
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Pages to Audio API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"] if settings.APP_ENV == "development" else [],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix=API_V1_PREFIX)
    app.include_router(admin_auth_router, prefix=API_V1_PREFIX)
    app.include_router(admin_settings_router, prefix=API_V1_PREFIX)
    app.include_router(admin_sessions_router, prefix=API_V1_PREFIX)
    app.include_router(gateway_router, prefix=API_V1_PREFIX)
    app.include_router(gateway_rgb_router, prefix=API_V1_PREFIX)
    app.include_router(handwritten_router, prefix=API_V1_PREFIX)
    app.include_router(knowledge_router, prefix=API_V1_PREFIX)

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={
                "error": type(exc).__name__,
                "reason_code": exc.reason_code,
                "message": str(exc),
            },
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": "InternalError", "reason_code": "INTERNAL_ERROR"},
        )

    return app
