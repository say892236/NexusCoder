"""Issue -> PR 后台编码流程的 AgentRun 持久化模型。

AgentRun 是整条链路的数据库锚点:API 创建它,Celery worker 更新执行状态
AgentLoop 的 token、Tool 调用与消息轨迹写回这里,最终再记录 Branch 和 PR 信息。
"""

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.base_class import BaseModel


class AgentRun(Base, BaseModel):
    """记录一次后台 Coding Agent 从排队到结束的完整执行快照。"""

    __tablename__ = "agent_runs"

    installation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository = Column(String(500), nullable=False, index=True)
    issue_number = Column(Integer, nullable=False, index=True)

    issue_title_snapshot = Column(Text, nullable=True)
    issue_body_snapshot = Column(Text, nullable=True)
    issue_url = Column(String(1000), nullable=True)
    custom_instructions = Column(Text, nullable=True)

    status = Column(
        Enum(
            "PENDING",
            "RUNNING",
            # Multi-Agent 已执行完成，
            # 当前暂停等待人工 Approve / Reject。
            "WAITING_FOR_APPROVAL",
            "COMPLETED",
            "FAILED",
            "CANCELED",
            name="agent_run_status_enum",
        ),
        nullable=False,
        default="PENDING",
        index=True,
    )
    celery_task_id = Column(String(255), nullable=True, index=True)

    iteration = Column(Integer, nullable=False, default=0)
    tokens_used = Column(Integer, nullable=False, default=0)
    tool_calls_made = Column(Integer, nullable=False, default=0)

    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    elapsed_seconds = Column(Integer, nullable=True)

    branch_name = Column(String(255), nullable=True)
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(String(1000), nullable=True)
    final_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    changed_files = Column(JSONB, nullable=False, default=list)

    # 保留完整原始载荷，供执行轨迹展示、问题定位和学习 Agent 推理过程使用。
    system_prompt = Column(Text, nullable=True)
    initial_user_message = Column(Text, nullable=True)
    conversation = Column(JSONB, nullable=False, default=list)
    final_result = Column(JSONB, nullable=False, default=dict)

    installation = relationship("Installation")
    user = relationship("User")

    def __repr__(self) -> str:
        """返回便于日志调试的字符串表示。"""
        return (
            f"<AgentRun(id={self.id}, repo={self.repository}, "
            f"issue={self.issue_number}, status={self.status})>"
        )
