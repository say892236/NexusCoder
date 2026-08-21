"""User model 的数据访问 Repository。

封装 GitHub OAuth 用户的创建、读取与更新，并在数据边界统一处理 token 加解密。
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_token, encrypt_token
from app.models.user import User


class UserRepository:
    """User model 的数据访问层。"""

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: UUID | str) -> User | None:
        """按 UUID 查询 User。

        Args:
            db: Database session
            user_id: User UUID (string or UUID object)

        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_github_id(db: AsyncSession, github_id: int) -> User | None:
        """按 GitHub ID 查询 User，主要用于 OAuth 登录。

        OAuth 认证时先用稳定的 GitHub ID 查询，再决定创建新用户还是更新现有用户。

        Args:
            db: Database session
            github_id: GitHub user ID from OAuth

        Returns:
            User object if found, None otherwise
        """
        result = await db.execute(select(User).where(User.github_id == github_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_all_active(db: AsyncSession, skip: int = 0, limit: int = 100) -> list[User]:
        """分页查询全部 active User。

        Args:
            db: Database session
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of active User objects
        """
        result = await db.execute(
            select(User).where(User.is_active == True).offset(skip).limit(limit)  # noqa: E712
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        github_id: int,
        username: str,
        email: str | None,
        avatar_url: str | None,
        access_token: str,
        refresh_token: str | None = None,
    ) -> User:
        """根据 GitHub OAuth 数据创建 User。

        OAuth token 入库前自动加密，并初始化 active 状态与最近登录时间。

        Args:
            db: Database session
            github_id: GitHub user ID
            username: GitHub username
            email: User's email from GitHub (may be None if private)
            avatar_url: GitHub avatar URL
            access_token: GitHub OAuth access token (will be encrypted)
            refresh_token: GitHub OAuth refresh token (will be encrypted)

        Returns:
            Created User object with all fields populated
        """
        user = User(
            github_id=github_id,
            username=username,
            email=email,
            avatar_url=avatar_url,
            access_token=encrypt_token(access_token),
            refresh_token=encrypt_token(refresh_token) if refresh_token else None,
            is_active=True,
            last_login_at=datetime.now(timezone.utc),
        )

        db.add(user)
        await db.flush()  # 分配 ID，但仍由外层控制事务提交。
        await db.refresh(user)  # 读取 ID、时间戳等数据库生成字段。

        return user

    @staticmethod
    async def update_tokens(
        db: AsyncSession,
        user: User,
        access_token: str,
        refresh_token: str | None = None,
    ) -> User:
        """在刷新或重新登录时更新用户 OAuth token。

        加密新 token 并更新最近登录时间，用于重新登录或 token 刷新场景。

        Args:
            db: Database session
            user: User object to update
            access_token: New GitHub OAuth access token
            refresh_token: New GitHub OAuth refresh token (optional)

        Returns:
            Updated User object
        """
        user.access_token = encrypt_token(access_token)
        if refresh_token:
            user.refresh_token = encrypt_token(refresh_token)
        user.last_login_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    async def update_profile(
        db: AsyncSession,
        user: User,
        username: str | None = None,
        email: str | None = None,
    ) -> User:
        """更新 User 资料。

        Args:
            db: Database session
            user: User object to update
            username: New username (optional)
            email: New email (optional)

        Returns:
            Updated User object
        """
        if username is not None:
            user.username = username
        if email is not None:
            user.email = email

        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    async def deactivate(db: AsyncSession, user: User) -> User:
        """软停用 User 账户。

        仅设置 ``is_active=False``，不物理删除记录。

        Args:
            db: Database session
            user: User object to deactivate

        Returns:
            Updated User object with is_active=False
        """
        user.is_active = False

        await db.flush()
        await db.refresh(user)

        return user

    @staticmethod
    def get_decrypted_access_token(user: User) -> str:
        """解密并返回用户的 GitHub access token。

        仅在需要代表用户调用 GitHub API 时使用；数据库中始终保存密文。

        Args:
            user: User object with encrypted access_token

        Returns:
            Decrypted GitHub OAuth access token
        """
        return decrypt_token(user.access_token)

    @staticmethod
    def get_decrypted_refresh_token(user: User) -> str | None:
        """解密并返回用户的 GitHub refresh token。

        Args:
            user: User object with encrypted refresh_token

        Returns:
            Decrypted GitHub OAuth refresh token, or None if not set
        """
        if user.refresh_token:
            return decrypt_token(user.refresh_token)
        return None
