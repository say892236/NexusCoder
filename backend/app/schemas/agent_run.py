"""后台 Coding AgentRun 的请求与响应 schema。"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LaunchAgentRequest(BaseModel):
    """启动后台 Coding Agent 的请求载荷。"""

    issue_number: int = Field(..., ge=1)
    repository: str = Field(..., description="Repository in format 'owner/repo'")
    custom_instructions: str | None = Field(default=None)


class LaunchAgentResponse(BaseModel):
    """AgentRun 成功入队后的响应载荷。"""

    agent_run_id: UUID
    celery_task_id: str
    message: str


class AgentRunListItemResponse(BaseModel):
    """列表视图使用的精简 AgentRun 数据。"""

    id: UUID
    issue_id: str
    repository: str
    issue_number: int
    status: str
    custom_instructions: str | None
    iteration: int
    tokens_used: int
    tool_calls_made: int
    started_at: datetime | None
    completed_at: datetime | None
    elapsed_seconds: int | None
    pr_url: str | None
    pr_number: int | None
    branch_name: str | None
    files_changed: list[str]
    error: str | None
    celery_task_id: str | None
    created_at: datetime


class AgentRunDetailResponse(AgentRunListItemResponse):
    """进度与详情视图使用的完整 AgentRun 数据。"""

    issue_title_snapshot: str | None
    issue_body_snapshot: str | None
    issue_url: str | None
    final_summary: str | None
    system_prompt: str | None
    initial_user_message: str | None
    conversation: list[dict[str, Any]]
    final_result: dict[str, Any]
