"""Installation model 的数据访问 Repository。

封装 GitHub App Installation 的创建、查询、配置更新与启停操作，并统一处理 JSONB 配置。
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.installation import Installation


class InstallationRepository:
    """Installation model 的数据访问层。

    集中封装 GitHub App Installation 查询，供 Repository 接入与 Review 配置管理使用。
    """

    @staticmethod
    async def get_by_id(db: AsyncSession, installation_id: UUID | str) -> Installation | None:
        """按 UUID 查询 Installation。

        Args:
            db: Database session
            installation_id: Installation UUID

        Returns:
            Installation object if found, None otherwise
        """
        result = await db.execute(select(Installation).where(Installation.id == installation_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_github_installation_id(
        db: AsyncSession, github_installation_id: int
    ) -> Installation | None:
        """按 GitHub Installation ID 查询 Installation。

        Args:
            db: Database session
            github_installation_id: GitHub App installation ID

        Returns:
            Installation object if found, None otherwise
        """
        result = await db.execute(
            select(Installation).where(
                Installation.github_installation_id == github_installation_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_repository(
        db: AsyncSession, repository: str, active_only: bool = True
    ) -> Installation | None:
        """按 Repository 名称查询 Installation。

        Args:
            db: Database session
            repository: Repository in format 'owner/repo'
            active_only: If True, only return active installations

        Returns:
            Installation object if found, None otherwise
        """
        query = select(Installation).where(Installation.repository == repository)

        if active_only:
            query = query.where(Installation.is_active == True)  # noqa: E712

        result = await db.execute(query)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_installations(
        db: AsyncSession, user_id: UUID | str, active_only: bool = True
    ) -> list[Installation]:
        """查询指定用户的全部 Installation。

        Args:
            db: Database session
            user_id: User UUID
            active_only: If True, only return active installations

        Returns:
            List of Installation objects
        """
        query = select(Installation).where(Installation.user_id == user_id)

        if active_only:
            query = query.where(Installation.is_active == True)  # noqa: E712

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        github_installation_id: int,
        user_id: UUID | str,
        account_type: str,
        account_name: str,
        repository: str,
        config: dict | None = None,
    ) -> Installation:
        """创建新的 Installation 记录。

        Args:
            db: Database session
            github_installation_id: GitHub App installation ID
            user_id: User UUID who owns this installation
            account_type: 'USER' or 'ORGANIZATION'
            account_name: GitHub account name
            repository: Repository in format 'owner/repo'
            config: Review configuration as dict (optional)

        Returns:
            Created Installation object
        """
        installation = Installation(
            github_installation_id=github_installation_id,
            user_id=user_id,
            account_type=account_type,
            account_name=account_name,
            repository=repository,
            config=config or {},
            is_active=True,
        )

        db.add(installation)
        await db.flush()
        await db.refresh(installation)

        return installation

    @staticmethod
    async def update_config(
        db: AsyncSession, installation: Installation, config: dict
    ) -> Installation:
        """更新 Installation 的 Review 配置。

        Args:
            db: Database session
            installation: Installation object to update
            config: New configuration dict (sensitivity, custom_instructions, etc.)

        Returns:
            Updated Installation object
        """
        installation.config = config

        await db.flush()
        await db.refresh(installation)

        return installation

    @staticmethod
    async def activate(db: AsyncSession, installation: Installation) -> Installation:
        """激活 Installation，即启用 Review。

        Args:
            db: Database session
            installation: Installation object to activate

        Returns:
            Updated Installation object with is_active=True
        """
        installation.is_active = True
        installation.suspended_at = None

        await db.flush()
        await db.refresh(installation)

        return installation

    @staticmethod
    async def deactivate(db: AsyncSession, installation: Installation) -> Installation:
        """软停用 Installation，即关闭 Review。

        设置 ``is_active=False`` 并记录停用时间；保留历史数据而非物理删除。

        Args:
            db: Database session
            installation: Installation object to deactivate

        Returns:
            Updated Installation object with is_active=False
        """
        installation.is_active = False
        installation.suspended_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(installation)

        return installation

    @staticmethod
    async def check_exists(db: AsyncSession, github_installation_id: int, repository: str) -> bool:
        """检查 Repository 是否已存在对应 Installation。

        用于阻止用户重复接入已经启用 Review 的 Repository。

        Args:
            db: Database session
            github_installation_id: GitHub App installation ID
            repository: Repository in format 'owner/repo'

        Returns:
            True if installation exists, False otherwise
        """
        result = await db.execute(
            select(Installation).where(
                and_(
                    Installation.github_installation_id == github_installation_id,
                    Installation.repository == repository,
                )
            )
        )
        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_active_count(db: AsyncSession, user_id: UUID | str) -> int:
        """统计用户当前 active 的 Installation 数量。

        可用于用量限制或 dashboard 统计。

        Args:
            db: Database session
            user_id: User UUID

        Returns:
            Number of active installations
        """
        from sqlalchemy import func

        result = await db.execute(
            select(func.count(Installation.id)).where(
                and_(Installation.user_id == user_id, Installation.is_active == True)  # noqa: E712
            )
        )
        count: int = result.scalar_one()
        return count
