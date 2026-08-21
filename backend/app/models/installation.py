"""GitHub App Installation 模型。

每条记录表示 Metis GitHub App 在特定 Repository 或组织中的一次 Installation，并保存
GitHub Installation ID 与 JSON 格式的 Review 配置，如敏感度和自定义规则。
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.base_class import BaseModel


class Installation(Base, BaseModel):
    """Repository 或组织上的 GitHub App Installation。

    将用户与特定 GitHub Installation 及其 Review 配置关联。``config`` 字段用 JSON
    保存 ReviewerConfig，以支持自定义敏感度、指令和忽略模式。
    """

    __tablename__ = "installations"
    __table_args__ = (
    # 一个 Installation 可覆盖多个 Repository，但二者组合必须唯一。
        Index(
            "ix_installations_github_installation_id_repository",
            "github_installation_id",
            "repository",
            unique=True,
        ),
    )

    # GitHub App Installation 标识。
    github_installation_id = Column(
        Integer,
        nullable=False,
        index=True,
        comment="GitHub App installation ID",
    )

    # Installation 所有者信息。
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Installation 目标 Repository。
    account_type = Column(
        Enum("USER", "ORGANIZATION", name="account_type_enum"),
        nullable=False,
        comment="Whether installed on user account or org",
    )
    account_name = Column(String(255), nullable=False, index=True)
    repository = Column(
        String(500),
        nullable=False,
        index=True,
        comment="Repository in format 'owner/repo'",
    )

    # Review 配置快照。
    config = Column(
        JSONB,
        nullable=False,
        default={},
        comment="ReviewerConfig as JSON: sensitivity, custom_instructions, etc.",
    )

    # 当前启用状态。
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    suspended_at = Column(DateTime(timezone=True), nullable=True)

    # ORM 关系。
    user = relationship("User", back_populates="installations")
    reviews = relationship("Review", back_populates="installation", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """返回便于日志调试的字符串表示。"""
        return f"<Installation(id={self.id}, repo={self.repository}, active={self.is_active})>"
