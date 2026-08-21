"""基于 Pydantic Settings 的应用配置管理。

集中声明环境变量与 .env 配置，并借助 Pydantic 完成类型转换和校验。
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量加载并校验的应用配置。"""

    # 应用基本信息。
    app_name: str = "Metis AI Code Reviewer"
    version: str = "0.1.0"
    debug: bool = False

    # HTTP Server 配置。
    host: str = "0.0.0.0"
    port: int = 8000

    # GitHub App 与 OAuth 配置。
    GITHUB_APP_ID: int | None = None
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET_ID: str | None = None
    GITHUB_APP_NAME: str | None = None
    GITHUB_SECRET_KEY_PATH: str | None = None
    GITHUB_WEBHOOK_SECRET: str | None = None
    GITHUB_INSTALLATION_ID: int | None = None

    # LLM Provider：使用 LiteLLM 模型格式，例如 ``vertex_ai/...`` 或 ``gpt-4o``。
    # Provider 列表见 https://docs.litellm.ai/docs/providers 。
    MODEL_NAME: str = "vertex_ai/zai-org/glm-4.7-maas"

    # Vertex AI 配置；Google Cloud 模型通过 gcloud CLI 的 ADC 认证。
    VERTEX_PROJECT: str | None = None
    VERTEX_LOCATION: str | None = None

    # 数据库配置。
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    DATABASE_ECHO: bool = False

    # JWT 配置。
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 前端 URL，用于 OAuth callback 与 CORS。
    FRONTEND_URL: str

    # OAuth token 的应用层加密密钥。
    ENCRYPTION_KEY: str

    # Redis 配置。
    REDIS_URL: str
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_SOCKET_KEEPALIVE: bool = True
    REDIS_SOCKET_TIMEOUT: int = 5

    # Celery broker、result backend 与超时配置。
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    CELERY_TASK_TIME_LIMIT: int = 600
    CELERY_TASK_SOFT_TIME_LIMIT: int = 540

    # Daytona Sandbox 配置。
    DAYTONA_API_KEY: str
    DAYTONA_API_URL: str
    DAYTONA_TARGET: str

    # LangSmith tracing 配置。
    LANGSMITH_TRACING: bool = True
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_ENDPOINT: str | None = None
    LANGSMITH_PROJECT: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


settings = Settings()

    # 导出 Vertex AI 环境变量，供 LiteLLM 自动识别。
if settings.VERTEX_PROJECT:
    os.environ["VERTEXAI_PROJECT"] = settings.VERTEX_PROJECT
if settings.VERTEX_LOCATION:
    os.environ["VERTEXAI_LOCATION"] = settings.VERTEX_LOCATION

    # 导出 LangSmith 环境变量，供其 SDK 读取。
if settings.LANGSMITH_TRACING:
    os.environ["LANGSMITH_TRACING"] = "true"
if settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
if settings.LANGSMITH_PROJECT:
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
if settings.LANGSMITH_ENDPOINT:
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
