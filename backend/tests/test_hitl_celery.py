
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.tasks import background_agent_task as m


@pytest.mark.asyncio
async def test_resume_approve_creates_pr(monkeypatch):
    """模拟人工批准，验证恢复、PR 创建和任务状态更新。"""

    # 1. 模拟数据库中的 AgentRun 和 GitHub Installation
    run = SimpleNamespace(
        id=uuid4(),
        installation_id=uuid4(),
        repository="demo/test-repo",
        issue_number=1,
        issue_title_snapshot="修复登录异常",
        status="WAITING_FOR_APPROVAL",
        started_at=None,
    )
    installation = SimpleNamespace(github_installation_id=123)

    db = AsyncMock()
    db.execute.side_effect = [
        SimpleNamespace(scalar_one_or_none=lambda: run),
        SimpleNamespace(scalar_one_or_none=lambda: installation),
    ]

    session = MagicMock()
    session.__aenter__.return_value = db
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: session)

    # 2. 模拟 LangGraph 恢复成功
    fake_resume = AsyncMock(return_value={
        "final_result": {"success": True},
        "code_result": {
            "summary": "已修复登录异常",
            "branch_name": "agent/fix-login",
        },
    })
    monkeypatch.setattr(m, "resume_multi_agent_graph", fake_resume)

    # 3. 模拟 GitHub API，不访问真实 GitHub
    github = MagicMock()
    github.get_repository = AsyncMock(
        return_value={"default_branch": "main"}
    )
    github.create_pull_request = AsyncMock(return_value={
        "number": 7,
        "html_url": "https://github.com/demo/test-repo/pull/7",
    })
    monkeypatch.setattr(m, "GitHubService", lambda: github)

    # 4. 执行 Celery 任务内部的异步业务逻辑
    task = SimpleNamespace(
        request=SimpleNamespace(id="mock-celery-task")
    )

    result = await m._resume_issue_after_approval_async(
        task, str(run.id), True
    )

    # 5. 验证结果
    fake_resume.assert_awaited_once_with(
        thread_id=str(run.id),
        approved=True,
    )
    github.create_pull_request.assert_awaited_once()

    assert result["status"] == "success"
    assert run.status == "COMPLETED"
    assert run.pr_number == 7
    assert run.pr_url.endswith("/pull/7")
    db.commit.assert_awaited()
