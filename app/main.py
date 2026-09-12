"""应用入口：``uvicorn app.main:app --reload``

职责：
- 创建 FastAPI 实例（默认 ``ORJSONResponse``，走 orjson 序列化）
- 启动时注入 truststore、关闭时释放共享连接池
- 把所有异常统一成 ``{"error": {code, message, detail}}`` 结构
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import orjson
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.adapters import UpstreamError, close_client
from app.config import Settings, get_settings
from app.models import ErrorDetail, ErrorResponse
from app.routers import lottery_router
from app.services.lottery_service import LotteryError


@asynccontextmanager
async def lifespan(app: FastAPI):
    # truststore 必须早于任何 TLS 连接建立
    if get_settings().upstream_use_truststore:
        import truststore

        truststore.inject_into_ssl()
    try:
        yield
    finally:
        # 释放共享连接池
        await close_client()


def _error(status_code: int, code: str, message: str, detail: Any = None) -> Response:
    """构造统一错误响应（用 orjson 序列化）。"""
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, detail=detail))
    return Response(
        content=orjson.dumps(body.model_dump()),
        status_code=status_code,
        media_type="application/json",
    )


def create_app() -> FastAPI:
    settings: Settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="多数据源彩票开奖聚合服务：配置驱动 + 适配器模式",
        debug=settings.debug,
        lifespan=lifespan,
    )

    # ---- 统一错误处理 ----
    @app.exception_handler(LotteryError)
    async def _handle_lottery_error(request: Request, exc: LotteryError) -> Response:
        # 业务错误：未知彩种 ID 等 -> 422
        return _error(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(UpstreamError)
    async def _handle_upstream_error(request: Request, exc: UpstreamError) -> Response:
        # 上游网络失败 / 业务错误码 / 无数据 -> 502
        return _error(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> Response:
        # 参数校验失败（含 limit 越界、路径类型错误）-> 422
        detail = [
            {"loc": list(item.get("loc", ())), "msg": item.get("msg"), "type": item.get("type")}
            for item in exc.errors()
        ]
        return _error(422, "invalid_parameter", "请求参数校验失败", detail)

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        # 404 等也走统一结构
        return _error(exc.status_code, "http_error", str(exc.detail), {"path": request.url.path})

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(lottery_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "endpoints": ["/lottery", "/lottery/{id}/latest", "/lottery/{id}/history"],
        }

    @app.get("/health", include_in_schema=False)
    async def health() -> dict:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
