"""Coding Agent 长期记忆持久化模型。

AgentMemory 保存从历史 AgentRun 中提炼出的可复用经验和仓库知识。
它不保存完整执行轨迹,完整原始轨迹仍由 AgentRun 负责。
"""

from sqlalchemy import Boolean, Column, Enum, ForeignKey, Integer, String, Text,DateTime
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.base_class import BaseModel
from pgvector.sqlalchemy import Vector

class AgentMemory(Base, BaseModel):
    """保存 Coding Agent 可跨任务复用的长期记忆。"""

    __tablename__ = "agent_memories"

    # Memory 属于哪个代码仓库。
    repository = Column(
        String(500),
        nullable=False,
        index=True,
    )

    # EPISODIC：
    #   某次任务中发生过的经验，例如：
    #   “修改 auth 模块后需要同时更新 test_auth.py。”
    #
    # SEMANTIC：
    #   相对稳定的仓库知识，例如：
    #   “该项目使用 pytest，测试目录为 tests/。”
    memory_type = Column(
        Enum(
            "EPISODIC",
            "SEMANTIC",
            name="agent_memory_type_enum",
        ),
        nullable=False,
        index=True,
    )

    # 用于识别“同一条知识”，以后做更新 / 合并 / 去重。
    #
    # 示例：
    # testing.command
    # auth.login_dependency
    # repository.python_version
    memory_key = Column(
        String(500),
        nullable=True,
        index=True,
    )

    # 给检索和 Prompt 使用的简短版本。
    summary = Column(
        Text,
        nullable=False,
    )

    # 更完整的记忆内容。
    content = Column(
        Text,
        nullable=False,
    )

        # Memory 的语义向量。
    # 第一版使用 1536 维 Embedding。
    # nullable=True 是为了兼容已经存在、尚未生成向量的旧 Memory。
    embedding = Column(
        Vector(1536),
        nullable=True,
    )

    # 这条 Memory 最初来自哪一次 AgentRun。
    # AgentRun 删除时不删除 Memory，因为经验可能仍然有价值。
    source_agent_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "agent_runs.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # 重要程度。
    # 先约定 1 ~ 5，后面 Memory Policy 会真正使用它。
    importance = Column(
        Integer,
        nullable=False,
        default=1,
    )

    # 为后续存标签、来源、证据等扩展信息预留。
    #
    # 示例：
    # {
    #     "issue_number": 12,
    #     "agent": "tester",
    #     "tags": ["pytest", "auth"]
    # }
    memory_metadata = Column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # 可选过期时间。
    # None 表示长期有效，主要用于稳定的 Semantic Memory。
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # 以后做删除 / 失效时优先软删除，不直接物理删除。
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    source_agent_run = relationship("AgentRun")

    def __repr__(self) -> str:
        """返回便于日志调试的字符串表示。"""
        return (
            f"<AgentMemory(id={self.id}, repo={self.repository}, "
            f"type={self.memory_type}, key={self.memory_key})>"
        )
