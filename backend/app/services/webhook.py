"""验证并处理 GitHub webhook，同时投递异步 Celery task。

webhook handler 只负责校验、保存 PENDING Review 和快速入队；耗时的 Sandbox 与 Agent
执行由 worker 完成，从而让 GitHub 请求能尽快收到响应。
"""

import hashlib
import hmac

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.installation import Installation
from app.repositories.review import ReviewRepository
from app.tasks.agent_review_task import process_pr_review_with_agent
from app.tasks.summary_task import process_pr_summary_with_agent


def verify_github_signature(payload: bytes, signature: str | None) -> bool:
    """验证 GitHub webhook 的 HMAC 签名。"""
    secret = settings.GITHUB_WEBHOOK_SECRET
    # GitHub 签名格式为 ``sha256=<signature>``。
    if not signature or not secret or not signature.startswith("sha256="):
        return False
    expected_signature = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected_signature)


async def handle_pull_request(
    action: str,
    pull_request: dict,
    repository: dict,
    installation: dict,
    db: AsyncSession,
) -> dict:
    """处理 pull_request webhook，并投递异步 Review task。

    1. 创建 PENDING Review 记录
    2. 投递 Celery task
    3. 立即返回（目标小于 500 ms）

    Args:
        action: PR 动作（opened、synchronize、reopened）
        pull_request: webhook 中的 PR 数据
        repository: webhook 中的 Repository 数据
        installation: webhook 中的 Installation 数据
        db: 数据库会话

    Returns:
        包含 status、task_id、review_id 的字典
    """
    # 仅处理 PR 创建、同步新 Commit 或重新打开事件。
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"Action '{action}' not handled"}

    # 提取 GitHub 的 Installation ID 与 Repository 上下文。
    github_installation_id = installation["id"]
    repo_full_name = repository["full_name"]
    pr_number = pull_request["number"]
    commit_sha = pull_request["head"]["sha"]

    # 必须同时按 GitHub Installation ID 和 Repository 查询，因为一个 Installation
    # 可以覆盖多个 Repository。
    installation_query = await db.execute(
        select(Installation).where(
            and_(
                Installation.github_installation_id == github_installation_id,
                Installation.repository == repo_full_name,
            )
        )
    )
    installation_record = installation_query.scalar_one_or_none()

    if not installation_record:
        # 找不到 Installation 表示用户尚未把该 Repository 接入 Metis。
        return {
            "status": "ignored",
            "reason": f"Installation {github_installation_id} not found. Repository not enrolled.",
        }

    # 先创建 PENDING Review 取得 review_id，再投递 worker。
    review_repo = ReviewRepository()
    review = await review_repo.create(
        db=db,
        installation_id=installation_record.id,  # 使用 Installation 表的 UUID 外键。
        repository=repo_full_name,
        pr_number=pr_number,
        commit_sha=commit_sha,
        metadata={
            "title": pull_request["title"],
            "author": pull_request["user"]["login"],
            "url": pull_request["html_url"],
            "head_branch": pull_request["head"]["ref"],
            "base_branch": pull_request["base"]["ref"],
            "language": pull_request["head"]["repo"]["language"],
        },
    )
    # 入队前先提交 Review，避免 worker 抢先查询到尚未提交的记录。
    await db.commit()

    # 投递 AI Agent Celery task；handler 无需等待 Review 完成。
    task = process_pr_review_with_agent.delay(
        review_id=str(review.id),
        installation_id=github_installation_id,  # worker 需要 GitHub 的整数 Installation ID。
        repository=repo_full_name,
        pr_number=pr_number,
    )

    summary_task = process_pr_summary_with_agent.delay(
        review_id=str(review.id),
        installation_id=github_installation_id,
        repository=repo_full_name,
        pr_number=pr_number,
        mode="append",
    )

    # 保存 Celery task ID，供状态查询与问题定位。
    review.celery_task_id = task.id
    review.pr_metadata = {
        **(review.pr_metadata or {}),
        "summary_task_id": summary_task.id,
        "summary_status": "QUEUED",
        "summary_mode": "append",
    }
    await db.commit()

    return {
        "status": "accepted",
        "message": f"Review queued for PR #{pr_number}",
        "task_id": task.id,
        "summary_task_id": summary_task.id,
        "review_id": str(review.id),
    }


def handle_ping() -> dict[str, str]:
    """处理 GitHub ping 事件。"""
    return {"status": "OK", "response": "ping"}


def handle_other_event(x_github_event: str) -> dict[str, str]:
    """处理当前未支持的 webhook 事件。"""
    return {"status": "OK", "response": f"event_{x_github_event}_not_handled"}
