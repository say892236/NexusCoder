"""GitHub API 集成服务。

负责 GitHub App JWT 与 Installation token 认证，并封装 Repository、Issue、PR、
Review comment 的读取和写入；Agent 与 Celery task 通过本服务隔离外部 API 细节。
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import jwt

from app.core.config import settings


class GitHubService:
    """封装 Metis 所需 GitHub API 的异步服务。"""

    def __init__(self) -> None:
        """初始化 GitHub API 客户端并加载 App 私钥。"""
        self.base_url = "https://api.github.com"
        self.app_id = settings.GITHUB_APP_ID
        self.private_key = self._load_private_key()
        self._client = httpx.AsyncClient(
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
        )

    def _load_private_key(self) -> str:
        """从配置路径读取 GitHub App 私钥。"""
        if settings.GITHUB_SECRET_KEY_PATH is None:
            raise ValueError("GitHub App private key path not configured")
        key_path = Path(settings.GITHUB_SECRET_KEY_PATH)
        if key_path.exists():
            return key_path.read_text()
        raise ValueError("GitHub App private key not configured")

    def _generate_jwt(self) -> str:
        """生成用于 GitHub App 身份认证的短期 JWT。"""
        now = datetime.now(timezone.utc)
        payload = {
            "iat": int(now.timestamp()) - 60,
            "exp": int((now + timedelta(minutes=10)).timestamp()),
            "iss": str(self.app_id),
        }
        token: str = jwt.encode(payload, self.private_key, algorithm="RS256")
        return token

    async def get_installation_token(self, installation_id: int) -> str:
        """为指定 Installation 获取短期 access token。"""
        jwt_token = self._generate_jwt()

        response = await self._client.post(
            f"{self.base_url}/app/installations/{installation_id}/access_tokens",
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        response.raise_for_status()

        data = response.json()
        token: str = data["token"]
        return token

    async def get_pr_diff(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int | None = None,
    ) -> str:
        """获取 PR diff 文本。

        Args:
            owner: Repository 所有者
            repo: Repository 名称
            pr_number: PR 编号
            installation_id: GitHub App Installation ID

        Returns:
            字符串形式的 PR diff
        """
        if installation_id is None:
            raise ValueError("installation_id is required for fetching PR diff")
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3.diff",
            },
        )
        response.raise_for_status()

        diff: str = response.text
        return diff

    async def create_pr_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        review_body: str,
        event: str = "COMMENT",
        installation_id: int | None = None,
    ) -> dict[str, Any]:
        """创建一条 PR Review。

        Args:
            owner: Repository 所有者
            repo: Repository 名称
            pr_number: PR 编号
            review_body: Review 主评论
            event: Review 事件类型（COMMENT、APPROVE、REQUEST_CHANGES）
            installation_id: GitHub App Installation ID

        Returns:
            GitHub API 响应数据
        """
        if installation_id is None:
            raise ValueError("installation_id is required for creating PR review")
        token = await self.get_installation_token(installation_id)

        payload = {
            "body": review_body,
            "event": event,
        }

        response = await self._client.post(
            f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()

        result: dict[str, Any] = response.json()
        return result

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        installation_id: int | None = None,
    ) -> dict[str, Any]:
        """以 JSON 字典读取 PR 详情。"""
        if installation_id is None:
            raise ValueError("installation_id is required for fetching pull request")
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def update_pr_description(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str | None = None,
        title: str | None = None,
        installation_id: int | None = None,
    ) -> dict[str, Any]:
        """更新 PR 标题或正文。"""
        if installation_id is None:
            raise ValueError("installation_id is required for updating PR description")
        if body is None and title is None:
            raise ValueError("At least one of body or title must be provided")
        token = await self.get_installation_token(installation_id)
        payload: dict[str, Any] = {}
        if body is not None:
            payload["body"] = body
        if title is not None:
            payload["title"] = title

        response = await self._client.patch(
            f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def create_pr_inline_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        token: str,
        body: str,
        path: str,
        line: int,
        commit_id: str,
        side: str = "RIGHT",
        start_line: int | None = None,
        start_side: str = "RIGHT",
    ) -> dict[str, Any]:
        """在 PR 的具体代码行创建一条 inline review comment。"""

        payload: dict[str, Any] = {
            "body": body,
            "path": path,
            "line": line,
            "side": side,
            "commit_id": commit_id,
        }
        if start_line is not None:
            payload["start_line"] = start_line
            payload["start_side"] = start_side

        response = await self._client.post(
            f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def create_pr_file_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        token: str,
        body: str,
        path: str,
        commit_id: str,
    ) -> dict[str, Any]:
        """在 PR 的文件层级创建一条 review comment。"""

        payload = {
            "body": body,
            "path": path,
            "subject_type": "file",
            "commit_id": commit_id,
        }

        response = await self._client.post(
            f"{self.base_url}/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    async def get_installation_repositories(self, installation_id: int) -> list[dict[str, Any]]:
        """读取指定 Installation 可访问的全部 Repository。

        使用 GitHub App Installation token 查询授权范围，用于向用户展示可接入
        Code Review 的 Repository。

        Args:
            installation_id: GitHub App Installation ID

        Returns:
            GitHub API 返回的 Repository 数据列表
        """
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/installation/repositories",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        data = response.json()
        repositories: list[dict[str, Any]] = data.get("repositories", [])
        return repositories

    async def get_user_installations_with_repos(
        self, user_access_token: str
    ) -> list[dict[str, Any]]:
        """读取用户的 GitHub App Installation 及各自可访问的 Repository。

        先使用用户 OAuth token 获取全部 Installation，再逐个读取其授权的 Repository。

        Args:
            user_access_token: 用户的 GitHub OAuth access token

        Returns:
            内嵌 Repository 列表的 Installation 数据
        """
        # 第一步读取用户的全部 Installation。
        response = await self._client.get(
            f"{self.base_url}/user/installations",
            headers={
                "Authorization": f"Bearer {user_access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        response.raise_for_status()

        data = response.json()
        installations = data.get("installations", [])

        # 第二步逐个补充 Installation 可访问的 Repository。
        installations_with_repos = []
        for installation in installations:
            installation_id = installation["id"]

            # 使用 Installation token 查询对应 Repository。
            try:
                repos = await self.get_installation_repositories(installation_id)

                installations_with_repos.append(
                    {
                        "id": installation_id,
                        "account": installation["account"],
                        "repository_selection": installation.get("repository_selection", "all"),
                        "repositories": repos,
                        "created_at": installation.get("created_at"),
                        "updated_at": installation.get("updated_at"),
                    }
                )
            except Exception as e:
                # 单个 Installation 无权访问时跳过，不影响其余结果。
                print(f"Warning: Could not fetch repos for installation {installation_id}: {e}")
                continue

        return installations_with_repos

    async def get_repository_issues(
        self,
        owner: str,
        repo: str,
        installation_id: int,
        state: str = "all",
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """读取 Repository 的 Issue 列表。

        Args:
            owner: Repository 所有者
            repo: Repository 名称
            installation_id: GitHub App Installation ID
            state: Issue 状态过滤条件（open、closed、all）
            per_page: 每页 Issue 数量，最多 100

        Returns:
            GitHub API 返回的 Issue 数据列表
        """
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/repos/{owner}/{repo}/issues",
            headers={"Authorization": f"Bearer {token}"},
            params={"state": state, "per_page": per_page},
        )
        response.raise_for_status()

        issues: list[dict[str, Any]] = response.json()
        # GitHub 的 Issue API 也返回 PR，此处显式排除带 pull_request 字段的项。
        issues = [issue for issue in issues if "pull_request" not in issue]
        return issues

    async def get_issue(
        self, owner: str, repo: str, issue_number: int, installation_id: int
    ) -> dict[str, Any]:
        """按编号读取单个 Issue。

        Args:
            owner: Repository 所有者
            repo: Repository 名称
            issue_number: Issue 编号
            installation_id: GitHub App Installation ID

        Returns:
            GitHub API 返回的 Issue 数据
        """
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        issue: dict[str, Any] = response.json()
        return issue

    async def get_issue_comments(
        self,
        owner: str,
        repo: str,
        issue_number: int,
        installation_id: int,
        per_page: int = 100,
    ) -> list[dict[str, Any]]:
        """读取 Issue 下的评论。

        Args:
            owner: Repository 所有者
            repo: Repository 名称
            issue_number: Issue 编号
            installation_id: GitHub App Installation ID
            per_page: 每页评论数量，最多 100

        Returns:
            GitHub API 返回的评论数据列表
        """
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": per_page},
        )
        response.raise_for_status()

        comments: list[dict[str, Any]] = response.json()
        return comments

    async def get_repository(
        self,
        owner: str,
        repo: str,
        installation_id: int,
    ) -> dict[str, Any]:
        """从 GitHub 读取 Repository metadata。"""
        token = await self.get_installation_token(installation_id)

        response = await self._client.get(
            f"{self.base_url}/repos/{owner}/{repo}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()

        repository_data: dict[str, Any] = response.json()
        return repository_data

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        installation_id: int,
    ) -> dict[str, Any]:
        """基于已推送的 head Branch 创建 PR。"""
        token = await self.get_installation_token(installation_id)

        response = await self._client.post(
            f"{self.base_url}/repos/{owner}/{repo}/pulls",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )
        response.raise_for_status()

        pr_data: dict[str, Any] = response.json()
        return pr_data


# 供通用调用方复用的模块级服务实例。
github_service = GitHubService()
