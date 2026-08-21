"""通过 GitHub OAuth 认证的 User 模型。

用户可管理不同 Repository 或组织上的多个 GitHub App Installation；用于 GitHub API 的
access token 加密保存，同时记录账户状态与登录活动。
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.db.base_class import BaseModel


class User(Base, BaseModel):
    """通过 GitHub OAuth 认证的用户账户。

    保存 GitHub 用户资料与加密 OAuth token。一个用户可关联多个 GitHub App
    Installation；所有 OAuth token 均在应用层加密后再入库。
    """

    __tablename__ = "users"

    # GitHub 用户资料。
    github_id = Column(
        Integer,
        unique=True,
        nullable=False,
        index=True,
        comment="GitHub user ID (immutable)",
    )
    username = Column(String(255), nullable=False, index=True)
    email = Column(String(255), nullable=True)
    avatar_url = Column(String(500), nullable=True)

    # 应用层加密后的 OAuth token。
    access_token = Column(String(500), nullable=False, comment="Encrypted GitHub OAuth token")
    refresh_token = Column(String(500), nullable=True, comment="Encrypted refresh token")

    # 账户状态与登录时间。
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # ORM 关系。
    installations = relationship(
        "Installation", back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """返回便于日志调试的字符串表示。"""
        return f"<User(id={self.id}, username={self.username}, github_id={self.github_id})>"
