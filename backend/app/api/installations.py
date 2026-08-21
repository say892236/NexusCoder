"""GitHub App Installation 管理 API。

用户可查看 GitHub Installation、为 Repository 启用或停用 Code Review，并维护敏感度、
自定义指令和忽略模式等 Review 配置。
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db.session import get_db
from app.models.installation import Installation
from app.models.user import User
from app.repositories.installation import InstallationRepository
from app.repositories.user import UserRepository
from app.schemas.installation import (
    EnableRepositoryRequest,
    InstallationResponse,
    SyncInstallationsResponse,
    UpdateConfigRequest,
)
from app.services.github import github_service

router = APIRouter(prefix="/installations")


@router.get("/github", response_model=list[dict[str, Any]])
async def list_github_installations(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """列出用户的 GitHub App Installation 及可访问 Repository。

    使用用户 OAuth token 从 GitHub API 获取授权范围，展示可启用 Code Review 的 Repository。

    Returns:
        内嵌 Repository 列表的 Installation 数据
    """
    # 仅在服务端解密 OAuth token，用于代表用户调用 GitHub API。
    github_token = UserRepository.get_decrypted_access_token(current_user)

    # 从 GitHub 获取 Installation 及其授权 Repository。
    installations = await github_service.get_user_installations_with_repos(github_token)

    return installations


@router.post("/sync", response_model=SyncInstallationsResponse)
async def sync_installations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SyncInstallationsResponse:
    """把用户的 GitHub Installation 同步到本地数据库。

    从 GitHub 获取当前 Installation 并创建或更新本地记录；同步本身只刷新可用数据，
    不等同于为 Repository 启用 Review。

    Returns:
        同步统计与 Installation 列表
    """
    # 解密当前用户的 GitHub token。
    github_token = UserRepository.get_decrypted_access_token(current_user)

    # 拉取 GitHub 当前授权范围。
    github_installations = await github_service.get_user_installations_with_repos(github_token)

    installation_repo = InstallationRepository()
    created_count = 0
    updated_count = 0

    synced_installations = []

    for gh_installation in github_installations:
        github_installation_id = gh_installation["id"]
        account = gh_installation["account"]
        repositories = gh_installation.get("repositories", [])

        # 根据 GitHub account.type 归一化账户类型。
        account_type = "ORGANIZATION" if account["type"] == "Organization" else "USER"

        # 一个 Installation 可能包含多个 Repository，逐个同步本地记录。
        for repo in repositories:
            repo_full_name = repo["full_name"]

            # 以 Installation ID 与 Repository 组合判断是否已存在。
            existing_query = await db.execute(
                select(Installation).where(
                    and_(
                        Installation.github_installation_id == github_installation_id,
                        Installation.repository == repo_full_name,
                    )
                )
            )
            existing = existing_query.scalar_one_or_none()

            if existing:
                # 已存在记录只刷新 GitHub 侧信息。
                updated_count += 1
                installation = existing
            else:
                # 新授权 Repository 创建本地 Installation，默认启用。
                installation = await installation_repo.create(
                    db=db,
                    github_installation_id=github_installation_id,
                    user_id=current_user.id,
                    account_type=account_type,
                    account_name=account["login"],
                    repository=repo_full_name,
                    config={
                        "sensitivity": "MEDIUM",
                        "custom_instructions": "",
                        "ignore_patterns": [],
                        "auto_review_enabled": True,
                    },
                )
                created_count += 1

            synced_installations.append(
                InstallationResponse(
                    id=str(installation.id),
                    github_installation_id=installation.github_installation_id,
                    user_id=str(installation.user_id),
                    account_type=installation.account_type,
                    account_name=installation.account_name,
                    repository=installation.repository,
                    config=installation.config,
                    is_active=installation.is_active,
                    created_at=installation.created_at.isoformat(),
                    updated_at=(
                        installation.updated_at.isoformat() if installation.updated_at else None
                    ),
                )
            )

    await db.commit()

    return SyncInstallationsResponse(
        synced=len(synced_installations),
        created=created_count,
        updated=updated_count,
        installations=synced_installations,
    )


@router.get("", response_model=list[InstallationResponse])
async def list_installations(
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InstallationResponse]:
    """从数据库列出用户已接入的 Installation。

    可选择只返回当前 active 的 Installation。

    Args:
        active_only: 为 True 时仅返回已启用记录

    Returns:
        数据库中的 Installation 记录列表
    """
    installation_repo = InstallationRepository()
    installations = await installation_repo.get_user_installations(
        db, current_user.id, active_only=active_only
    )

    return [
        InstallationResponse(
            id=str(inst.id),
            github_installation_id=inst.github_installation_id,
            user_id=str(inst.user_id),
            account_type=inst.account_type,
            account_name=inst.account_name,
            repository=inst.repository,
            config=inst.config,
            is_active=inst.is_active,
            created_at=inst.created_at.isoformat(),
            updated_at=inst.updated_at.isoformat() if inst.updated_at else None,
        )
        for inst in installations
    ]


@router.post("/enable", response_model=InstallationResponse, status_code=status.HTTP_201_CREATED)
async def enable_repository(
    request: EnableRepositoryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InstallationResponse:
    """为 Repository 启用 Code Review。

    记录不存在时创建 Installation，已存在但停用时重新激活；用户必须拥有对应 GitHub
    Installation 的访问权限。

    Args:
        request: Repository and configuration details

    Returns:
        Created or updated installation

    Raises:
        409: Repository already enabled
    """
    installation_repo = InstallationRepository()

    # 检查该 Repository 是否已有本地 Installation。
    existing_installation = await db.execute(
        select(Installation).where(
            and_(
                Installation.github_installation_id == request.github_installation_id,
                Installation.repository == request.repository,
            )
        )
    )
    installation = existing_installation.scalar_one_or_none()

    if installation:
        # 已有记录时区分已启用与可重新激活两种情况。
        if installation.is_active:
            # 已启用属于冲突，避免重复接入。
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Repository {request.repository} is already enabled",
            )
        # 重新激活之前停用的 Installation。
        installation = await installation_repo.activate(db, installation)
        installation = await installation_repo.update_config(
            db, installation, request.config.model_dump()
        )
        await db.commit()
    else:
    # 首次接入时创建新 Installation。
        installation = await installation_repo.create(
            db=db,
            github_installation_id=request.github_installation_id,
            user_id=current_user.id,
            account_type=request.account_type,
            account_name=request.account_name,
            repository=request.repository,
            config=request.config.model_dump(),
        )
        await db.commit()

    return InstallationResponse(
        id=str(installation.id),
        github_installation_id=installation.github_installation_id,
        user_id=str(installation.user_id),
        account_type=installation.account_type,
        account_name=installation.account_name,
        repository=installation.repository,
        config=installation.config,
        is_active=installation.is_active,
        created_at=installation.created_at.isoformat(),
        updated_at=(installation.updated_at.isoformat() if installation.updated_at else None),
    )


@router.put("/{installation_id}/config", response_model=InstallationResponse)
async def update_installation_config(
    installation_id: UUID,
    request: UpdateConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InstallationResponse:
    """更新 Installation 的 Review 配置。

    支持更新敏感度、自定义指令和忽略模式。

    Args:
        installation_id: Installation UUID
        request: Updated configuration

    Returns:
        Updated installation

    Raises:
        404: Installation not found
        403: User doesn't own this installation
    """
    installation_repo = InstallationRepository()
    installation = await installation_repo.get_by_id(db, installation_id)

    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Installation not found",
        )

    # 修改前验证 Installation 归属当前用户。
    if installation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this installation",
        )

    # 仅更新请求中明确提供的配置字段。
    installation = await installation_repo.update_config(
        db, installation, request.config.model_dump()
    )
    await db.commit()

    return InstallationResponse(
        id=str(installation.id),
        github_installation_id=installation.github_installation_id,
        user_id=str(installation.user_id),
        account_type=installation.account_type,
        account_name=installation.account_name,
        repository=installation.repository,
        config=installation.config,
        is_active=installation.is_active,
        created_at=installation.created_at.isoformat(),
        updated_at=(installation.updated_at.isoformat() if installation.updated_at else None),
    )


@router.delete("/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_installation(
    installation_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """停用 Installation 的 Code Review。

    将 ``is_active`` 设为 False，后续仍可重新启用。

    Args:
        installation_id: Installation UUID

    Raises:
        404: Installation not found
        403: User doesn't own this installation
    """
    installation_repo = InstallationRepository()
    installation = await installation_repo.get_by_id(db, installation_id)

    if not installation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Installation not found",
        )

    # 停用前验证 Installation 归属当前用户。
    if installation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this installation",
        )

    # 软停用并保留历史数据。
    await installation_repo.deactivate(db, installation)
    await db.commit()
