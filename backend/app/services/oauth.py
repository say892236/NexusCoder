"""用于用户认证的 GitHub OAuth 服务。

封装授权跳转、authorization code 换取 token、读取用户资料的完整 OAuth 流程，
上层 API 再把结果用于创建或更新 User。
"""

from typing import Any

import httpx

from app.core.config import settings


class GitHubOAuthService:
    """GitHub OAuth 认证流程服务。

    实现三段式流程：跳转 GitHub 授权、接收携带 authorization code 的 callback、
    用 code 换取 access token 并获取用户资料。
    """

    def __init__(self) -> None:
        """使用 GitHub OAuth API endpoint 初始化服务。"""
        self.authorize_url = "https://github.com/login/oauth/authorize"
        self.token_url = "https://github.com/login/oauth/access_token"
        self.user_api_url = "https://api.github.com/user"
        self.installations_url = "https://api.github.com/user/installations"

    def get_authorization_url(self) -> str:
        """生成 GitHub OAuth 授权 URL。"""
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": "http://localhost:8000/auth/callback/github",
            "scope": "user:email read:org",  # 当前登录与邮箱读取流程需要的 scope。
        }

        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.authorize_url}?{query_string}"

    async def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """用 authorization code 换取 access token。

        用户授权后 GitHub 携带 code 跳回应用；服务用该 code 换取 access token，
        之后应用才能代表用户调用 GitHub API。
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET_ID,
                    "code": code,
                },
            )
            response.raise_for_status()

            data: dict[str, Any] = response.json()

            if "error" in data:
                raise ValueError(f"GitHub OAuth error: {data.get('error_description')}")

            return data

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """从 GitHub API 读取用户资料。

        使用 access token 获取用户名、邮箱、头像和唯一 GitHub ID。
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.user_api_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()

            user_data: dict[str, Any] = response.json()
            return user_data

    async def get_user_installations(self, access_token: str) -> dict[str, Any]:
        """读取用户的 GitHub App Installation。

        返回用户安装 NexusCoder GitHub App 的 Repository 或组织，供 Repository 接入流程使用。
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.installations_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()

            data: dict[str, Any] = response.json()
            return data


# 供依赖方复用的模块级服务实例。
github_oauth = GitHubOAuthService()
