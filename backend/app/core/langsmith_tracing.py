"""LangSmith Trace 全局配置与敏感字段脱敏。"""

from typing import Any

from langsmith import Client
from langsmith.run_trees import configure

from app.core.config import settings


SENSITIVE_TRACE_KEYS = {
    "issue_body",
    "custom_instructions",
    "system_prompt",
    "initial_user_message",
    "conversation",
    "messages",
}


def _sanitize_trace_value(value: Any) -> Any:
    """递归清理不应上传到 LangSmith 的业务正文。"""

    if isinstance(value, dict):
        sanitized = {}

        for key, item in value.items():
            if key in SENSITIVE_TRACE_KEYS:
                sanitized[key] = "<redacted>"
            else:
                sanitized[key] = _sanitize_trace_value(item)

        return sanitized

    if isinstance(value, list):
        return [_sanitize_trace_value(item) for item in value]

    return value


def sanitize_trace_data(data: dict) -> dict:
    """保留结构信息，但隐藏敏感正文。"""

    return _sanitize_trace_value(data)


def configure_langsmith_tracing() -> None:
    """初始化项目统一 LangSmith tracing。"""

    if not settings.LANGSMITH_TRACING:
        return

    client = Client(
        api_key=settings.LANGSMITH_API_KEY,
        api_url=settings.LANGSMITH_ENDPOINT,
        hide_inputs=sanitize_trace_data,
        hide_outputs=sanitize_trace_data,
    )

    configure(
        client=client,
        enabled=True,
        project_name=settings.LANGSMITH_PROJECT,
    )
