"""面向 Agent 的 Daytona SDK Sandbox 客户端封装。

该层负责创建远程 Runtime、设置资源与自动停止策略，并把 Repository clone 到固定工作目录；
更高层的 SandboxManager 再按 agent_id 管理复用和销毁。
"""
import uuid

from daytona import CreateSandboxFromSnapshotParams, Daytona, DaytonaConfig

from app.core.config import settings


class DaytonaClient:
    """把 Daytona SDK 适配为 NexusCoder Agent 所需的最小 Sandbox 接口。"""

    def __init__(self, git_username: str | None = None, git_token: str | None = None):
        """使用应用配置和可选 Git 凭据初始化 Daytona 客户端。

        Args:
            git_username: Git 认证用户名，默认 ``git``
            git_token: Git 认证 token
        """
        self._client = Daytona(
            DaytonaConfig(
                api_key=settings.DAYTONA_API_KEY,
                api_url=settings.DAYTONA_API_URL,
                target=settings.DAYTONA_TARGET,
            )
        )
        self.git_username = git_username or "git"
        self.git_token = git_token

    def _initialize_git(self, sandbox):
        """
        初始化 Sandbox 内 git 配置。

        Daytona Sandbox 是临时环境，
        默认没有 git user.name / user.email。
        如果不初始化，commit 会失败。
        """

        sandbox.process.exec(
            command=(
                'git config user.name "NexusCoder" '
                '&& '
                'git config user.email "metis-ai@example.com"'
            ),
            cwd="workspace/repo",
            timeout=30,
        )

    def create_sandbox(
        self,
        agent_id: str,
        repository_url: str | None = None,
        branch: str | None = None,
        language: str = "python",
        snapshot: str | None = None,
    ):
        """创建 Daytona Sandbox，并按需 clone Repository。

        Args:
            agent_id: Agent 唯一 ID，同时用于 Sandbox 名称
            repository_url: 可选的 Git Repository 地址
            language: Runtime 语言，支持 Python、TypeScript、JavaScript
            snapshot: 可选的自定义 snapshot 名称

        Returns:
            Daytona Sandbox 实例
        """
        params = CreateSandboxFromSnapshotParams(
            name=f"agent-{agent_id}-{uuid.uuid4().hex[:6]}",
            language=language,
            snapshot=snapshot,
            shell="/bin/bash",
            resources={
                "cpu": 2,  # 2 个 vCPU
                "memory": 4,  # 4 GB 内存
                "disk": 8,  # 2 GB 磁盘
            },
            auto_stop_interval=15,  # 空闲 15 分钟后自动停止以节省资源。
            auto_delete_interval=-1,  # 不让 Daytona 自动删除，由 manager 显式释放。
            ephemeral=False,  # stop 后保留 Sandbox，允许重新启动。
        )

        # 创建远程 Runtime；timeout=0 的具体等待语义由 Daytona SDK 负责。
        sandbox = self._client.create(params, timeout=0)

        # 有 Repository 地址时，在返回前完成 clone。
        if repository_url:
            self._clone_repository(
                sandbox,
                repository_url,
                branch
            )

        # 初始化 Sandbox 内 git 用户信息
        self._initialize_git(sandbox)

        return sandbox

    def _clone_repository(self, sandbox, repository_url: str, branch: str | None = None) -> None:
        """把 Git Repository clone 到 Sandbox 的固定工作目录。

        Args:
            sandbox: Daytona Sandbox 实例
            repository_url: Git Repository 地址
            branch: 指定要 clone 的 Branch
        """
        # 使用 Daytona 内置 Git API，并把认证信息限制在 clone 操作中。
        sandbox.git.clone(
            url=repository_url,
            path="workspace/repo",
            branch=branch,  # Review 场景 clone PR Branch；Coding 场景 clone 默认 Branch。
            username=self.git_username,
            password=self.git_token,
        )

    def find_sandbox(self, sandbox_id: str):
        """按 ID 查找已存在的 Sandbox。

        Args:
            sandbox_id: Daytona Sandbox ID

        Returns:
            找到时返回 Daytona Sandbox，否则返回 None
        """
        try:
            return self._client.find_one(sandbox_id)
        except Exception:
            return None
