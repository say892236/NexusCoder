"""GitHub Issue 相关 API endpoint。

Issue 与 comment 不在本地数据库重复存储，而是每次从 GitHub API 动态读取最新数据；
本地 Installation 只用于确认当前用户已接入该 Repository 并取得认证信息。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_deps import get_current_user
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.installation import Installation
from app.models.user import User
from app.schemas.agent_run import AgentRunListItemResponse
from app.schemas.issue import IssueCommentResponse, IssueResponse
from app.services.github import GitHubService

logger = logging.getLogger(__name__)

router = APIRouter()


def _serialize_agent_run(run: AgentRun) -> AgentRunListItemResponse:
    return AgentRunListItemResponse(
        id=run.id,
        issue_id=f"{run.repository}#{run.issue_number}",
        repository=run.repository,
        issue_number=run.issue_number,
        status=str(run.status),
        custom_instructions=run.custom_instructions,
        iteration=run.iteration or 0,
        tokens_used=run.tokens_used or 0,
        tool_calls_made=run.tool_calls_made or 0,
        started_at=run.started_at,
        completed_at=run.completed_at,
        elapsed_seconds=run.elapsed_seconds,
        pr_url=run.pr_url,
        pr_number=run.pr_number,
        branch_name=run.branch_name,
        files_changed=run.changed_files or [],
        error=run.error,
        celery_task_id=run.celery_task_id,
        created_at=run.created_at,
    )


def _transform_github_issue(issue_data: dict[str, Any], repository: str) -> IssueResponse:
    """把 GitHub API 的原始 Issue 数据转换为 IssueResponse。

    Args:
        issue_data: GitHub API 返回的原始 Issue 数据
        repository: ``owner/repo`` 格式的 Repository

    Returns:
        IssueResponse 对象
    """
    return IssueResponse(
        id=issue_data["id"],
        repository=repository,
        issue_number=issue_data["number"],
        title=issue_data["title"],
        body=issue_data.get("body"),
        status="OPEN" if issue_data["state"] == "open" else "CLOSED",
        labels=[label["name"] for label in issue_data.get("labels", [])],
        assignees=[assignee["login"] for assignee in issue_data.get("assignees", [])],
        author=issue_data["user"]["login"],
        created_at=issue_data["created_at"],
        updated_at=issue_data.get("updated_at"),
        closed_at=issue_data.get("closed_at"),
        comments_count=issue_data.get("comments", 0),
        github_url=issue_data["html_url"],
    )


def _transform_github_comment(
    comment_data: dict[str, Any], issue_number: int
) -> IssueCommentResponse:
    """把 GitHub API 的原始评论数据转换为 IssueCommentResponse。

    Args:
        comment_data: GitHub API 返回的原始评论数据
        issue_number: 评论所属 Issue 编号

    Returns:
        IssueCommentResponse 对象
    """
    return IssueCommentResponse(
        id=comment_data["id"],
        issue_number=issue_number,
        author=comment_data["user"]["login"],
        avatar_url=comment_data["user"].get("avatar_url"),
        body=comment_data["body"],
        created_at=comment_data["created_at"],
        github_url=comment_data["html_url"],
    )


@router.get("/issues", response_model=list[IssueResponse])
async def list_issues(
    repository: str = Query(..., description="Repository in format 'owner/repo'"),
    state: str = Query("all", description="Issue state filter (open, closed, all)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IssueResponse]:
    """列出 Repository 的全部 Issue。

    数据从 GitHub API 动态读取，且 Repository 必须已接入 NexusCoder。

    Args:
        repository: Repository 全名（owner/repo）
        state: Issue 状态过滤条件（open、closed、all）
        current_user: 当前已认证用户
        db: 数据库会话

    Returns:
        Repository 的 Issue 列表

    Raises:
        HTTPException: Repository 不存在或尚未接入时抛出
    """
    logger.info(f"Fetching issues for repository: {repository}, state: {state}")

    # 仅允许当前用户查询自己已接入的 Repository。
    query = await db.execute(
        select(Installation).where(
            and_(
                Installation.repository == repository,
                Installation.user_id == current_user.id,
                Installation.is_active == True,  # noqa: E712
            )
        )
    )
    installation = query.scalar_one_or_none()

    if not installation:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {repository} not found or not enrolled in NexusCoder",
        )

    # 将 Repository 全名拆分为 GitHub API 所需的 owner/repo。
    try:
        owner, repo = repository.split("/")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository format. Use 'owner/repo'")

    # 使用 Installation 身份从 GitHub 获取最新 Issue。
    github = GitHubService()
    try:
        github_issues = await github.get_repository_issues(
            owner=owner,
            repo=repo,
            installation_id=installation.github_installation_id,
            state=state,
        )

    # 统一转换为前后端约定的响应 schema。
        issues = [_transform_github_issue(issue, repository) for issue in github_issues]

        logger.info(f"Found {len(issues)} issues for {repository}")
        return issues

    except Exception as e:
        logger.error(f"Failed to fetch issues from GitHub: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch issues: {e!s}")


@router.get("/issues/{issue_number}", response_model=IssueResponse)
async def get_issue(
    issue_number: int,
    repository: str = Query(..., description="Repository in format 'owner/repo'"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IssueResponse:
    """按编号读取单个 Issue。

    Issue 从 GitHub API 动态读取。

    Args:
        issue_number: GitHub Issue 编号
        repository: Repository 全名（owner/repo）
        current_user: 当前已认证用户
        db: 数据库会话

    Returns:
        Issue 详情

    Raises:
        HTTPException: Repository 或 Issue 不存在时抛出
    """
    logger.info(f"Fetching issue #{issue_number} for repository: {repository}")

    # 查询当前用户在该 Repository 上的 Installation。
    query = await db.execute(
        select(Installation).where(
            and_(
                Installation.repository == repository,
                Installation.user_id == current_user.id,
                Installation.is_active == True,  # noqa: E712
            )
        )
    )
    installation = query.scalar_one_or_none()

    if not installation:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {repository} not found or not enrolled",
        )

    # 拆分 owner/repo。
    try:
        owner, repo = repository.split("/")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository format. Use 'owner/repo'")

    # 从 GitHub 读取最新 Issue。
    github = GitHubService()
    try:
        github_issue = await github.get_issue(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            installation_id=installation.github_installation_id,
        )

        issue = _transform_github_issue(github_issue, repository)
        return issue

    except Exception as e:
        logger.error(f"Failed to fetch issue from GitHub: {e}", exc_info=True)
        if "404" in str(e):
            raise HTTPException(status_code=404, detail=f"Issue #{issue_number} not found")
        raise HTTPException(status_code=500, detail=f"Failed to fetch issue: {e!s}")


@router.get("/issues/{issue_number}/comments", response_model=list[IssueCommentResponse])
async def get_issue_comments(
    issue_number: int,
    repository: str = Query(..., description="Repository in format 'owner/repo'"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IssueCommentResponse]:
    """读取 Issue 的全部评论。

    评论从 GitHub API 动态读取。

    Args:
        issue_number: GitHub Issue 编号
        repository: Repository 全名（owner/repo）
        current_user: 当前已认证用户
        db: 数据库会话

    Returns:
        Issue 评论列表

    Raises:
        HTTPException: Repository 或 Issue 不存在时抛出
    """
    logger.info(f"Fetching comments for issue #{issue_number} in {repository}")

    # 查询当前用户在该 Repository 上的 Installation。
    query = await db.execute(
        select(Installation).where(
            and_(
                Installation.repository == repository,
                Installation.user_id == current_user.id,
                Installation.is_active == True,  # noqa: E712
            )
        )
    )
    installation = query.scalar_one_or_none()

    if not installation:
        raise HTTPException(
            status_code=404,
            detail=f"Repository {repository} not found or not enrolled",
        )

    # 拆分 owner/repo。
    try:
        owner, repo = repository.split("/")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid repository format. Use 'owner/repo'")

    # 从 GitHub 读取最新评论。
    github = GitHubService()
    try:
        github_comments = await github.get_issue_comments(
            owner=owner,
            repo=repo,
            issue_number=issue_number,
            installation_id=installation.github_installation_id,
        )

    # 转换为前后端约定的评论 schema。
        comments = [_transform_github_comment(comment, issue_number) for comment in github_comments]

        logger.info(f"Found {len(comments)} comments for issue #{issue_number}")
        return comments

    except Exception as e:
        logger.error(f"Failed to fetch comments from GitHub: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch comments: {e!s}")


@router.get(
    "/issues/{issue_number}/agent-runs",
    response_model=list[AgentRunListItemResponse],
)
async def list_issue_agent_runs(
    issue_number: int,
    repository: str = Query(..., description="Repository in format 'owner/repo'"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRunListItemResponse]:
    """列出 Repository 某个 Issue 对应的后台 AgentRun。"""
    rows = (
        (
            await db.execute(
                select(AgentRun)
                .where(
                    and_(
                        AgentRun.user_id == current_user.id,
                        AgentRun.repository == repository,
                        AgentRun.issue_number == issue_number,
                    )
                )
                .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_serialize_agent_run(run) for run in rows]
