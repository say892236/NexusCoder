"""FastAPI 应用主入口。

创建应用实例、配置 middleware、注册各业务 router，并暴露根路径与健康检查 endpoint。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agents,
    analytics,
    auth,
    installations,
    issues,
    review_comments,
    webhooks,
)
from app.core.config import settings


def create_application() -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        debug=settings.debug,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_URL],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 API router；各模块负责自己的 path prefix。
    app.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
    app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
    app.include_router(installations.router, prefix="/api", tags=["Installations"])
    app.include_router(agents.router, prefix="/api", tags=["Agents"])
    app.include_router(issues.router, prefix="/api", tags=["Issues"])
    app.include_router(review_comments.router, prefix="/api", tags=["Review Comments"])
    app.include_router(analytics.router, prefix="/api", tags=["Analytics"])

    return app


# 模块加载时创建 ASGI app 实例，供 Uvicorn 启动。
app = create_application()


@app.get("/")
async def root() -> dict[str, str]:
    """返回服务基本信息的根 endpoint。"""
    return {"name": settings.app_name, "version": settings.version, "status": "running"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    """供部署平台与监控系统探活的健康检查 endpoint。"""
    return {"status": "healthy", "app": settings.app_name, "version": settings.version}
