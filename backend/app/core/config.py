"""基于 Pydantic Settings 的应用配置管理。

集中声明环境变量与 .env 配置，并借助 Pydantic 完成类型转换和校验。
"""

import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()

class Settings(BaseSettings):
    """从环境变量加载并校验的应用配置。"""

    # Multi Agent 开发阶段使用 Mock Sandbox
    MOCK_SANDBOX: bool = True

    #mock llm
    MOCK_LLM: bool = True


    # 应用基本信息。
    app_name: str = "NexusCoder"
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

    # LLM Provider：使用 LiteLLM 模型格式
    # Provider 列表见 https://docs.litellm.ai/docs/providers 。
    MODEL_NAME: str = "deepseek/deepseek-v4-flash"
    DEEPSEEK_API_KEY: str | None = None

    # Memory Embedding 配置。
    MEMORY_EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    MEMORY_EMBEDDING_DIMENSIONS: int = 1536

    # 开发 / 测试阶段使用确定性的 Mock Embedding，
    # 避免测试依赖真实外部 API。
    MOCK_EMBEDDING: bool = True

    OPENAI_API_KEY: str | None = None

        # Semantic Recall 最大余弦距离。
    # cosine distance 越小表示越相似。
    MEMORY_MAX_COSINE_DISTANCE: float = 0.8


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
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_ENDPOINT: str | None = None
    LANGSMITH_PROJECT: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )


settings = Settings()

    # 导出 LangSmith 环境变量，供其 SDK 读取。
if settings.LANGSMITH_TRACING:
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_TRACING_V2"] = "true"
if settings.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = settings.LANGSMITH_API_KEY
if settings.LANGSMITH_PROJECT:
    os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
if settings.LANGSMITH_ENDPOINT:
    os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
