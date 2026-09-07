"""PR Code Review 与行级评论模型。

Review 表示一次由 AI Agent 生成的整体 PR 审查，ReviewComment 表示具体代码行上的独立
评论。分离建模便于单独查询评论，也对应 GitHub Review API 的多条 inline comment 结构。
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.base_class import BaseModel


class Review(Base, BaseModel):
    """由 AI Agent 生成的一次 PR Code Review。

    跟踪 Review 从 pending 到 completed/failed 的生命周期，保存整体审查文本和 PR
    metadata；每条 Review 归属一个 Installation，并可包含多条行级评论。
    """

    __tablename__ = "reviews"

    # 对应的 Celery task ID。
    celery_task_id = Column(
        String(255), nullable=True, index=True, comment="Celery task ID for tracking"
    )

    # 关联 GitHub App Installation。
    installation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # PR 基本信息。
    pr_number = Column(Integer, nullable=False, index=True)
    repository = Column(String(500), nullable=False, index=True)
    commit_sha = Column(String(40), nullable=False, comment="Git commit SHA being reviewed")

    # Review 生命周期状态。
    status = Column(
        Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", name="review_status_enum"),
        nullable=False,
        default="PENDING",
        index=True,
    )

    # Review 最终内容。
    review_text = Column(Text, nullable=True, comment="Overall review summary")

    # PR metadata；避开 SQLAlchemy 保留名 ``metadata``，因此使用 pr_metadata。
    pr_metadata = Column(
        JSONB,
        default={},
        comment="PR title, author, description, file count, etc.",
    )

    # Agent 处理信息与错误。
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    error = Column(Text, nullable=True, comment="Error message if status=FAILED")

    # GitHub 发布结果。
    github_review_id = Column(Integer, nullable=True, comment="GitHub API review ID")

    # ORM 关系。
    installation = relationship("Installation", back_populates="reviews")
    comments = relationship("ReviewComment", back_populates="review", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        """返回便于日志调试的字符串表示。"""
        return f"<Review(id={self.id}, repo={self.repository}, pr={self.pr_number}, status={self.status})>"


class ReviewComment(Base, BaseModel):
    """定位到具体代码行的一条 inline comment。

    表示 NexusCoder Agent 发现的一个代码问题，包含严重级别、类别，以及发布后的可选
    GitHub comment ID；通过 ``line_end`` 同时支持单行和多行评论。
    """

    __tablename__ = "review_comments"

    # 关联所属 Review。
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 问题在代码中的位置。
    file_path = Column(String(1000), nullable=False, index=True)
    line_number = Column(Integer, nullable=False)
    line_end = Column(Integer, nullable=True, comment="For multi-line comments")

    # 评论内容。
    title = Column(String(255), nullable=True, comment="Short finding title")
    comment_text = Column(Text, nullable=False)

    # 问题分类与严重级别。
    severity = Column(
        Enum("INFO", "WARNING", "ERROR", "CRITICAL", name="severity_enum"),
        nullable=False,
        index=True,
    )
    category = Column(
        Enum(
            "BUG",
            "SECURITY",
            "PERFORMANCE",
            "STYLE",
            "MAINTAINABILITY",
            "DOCUMENTATION",
            "TESTING",
            name="category_enum",
        ),
        nullable=False,
        index=True,
    )

    # GitHub 发布结果。
    github_comment_id = Column(BigInteger, nullable=True, comment="GitHub API comment ID (bigint)")

    # ORM 关系。
    review = relationship("Review", back_populates="comments")

    def __repr__(self) -> str:
        """返回便于日志调试的字符串表示。"""
        return f"<ReviewComment(id={self.id}, file={self.file_path}:{self.line_number}, severity={self.severity})>"
