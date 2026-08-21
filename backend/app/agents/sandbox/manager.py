"""管理 Agent 使用的 Daytona Sandbox 生命周期。

生命周期为 ``acquire -> reuse/start -> release/delete``。manager 在进程内用 agent_id
保存活动实例；停止的 Sandbox 可重新 start，任务 finally 阶段调用 release 完成删除。
"""

from typing import Any

from app.agents.sandbox.client import DaytonaClient


class SandboxManager:
    """按 agent_id 管理 Daytona Sandbox 的获取、停止与释放。"""

    def __init__(self, git_username: str | None = None, git_token: str | None = None):
        """使用 Git 凭据初始化 SandboxManager。

        Args:
            git_username: Git 认证用户名
            git_token: Git 认证 token
        """
        self.client = DaytonaClient(git_username=git_username, git_token=git_token)
        self._active_sandboxes: dict[str, Any] = {}

    def acquire(
        self,
        agent_id: str,
        repository_url: str | None = None,
        branch: str | None = None,
        language: str = "python",
    ):
        """为 Agent 获取可运行的 Sandbox。

        Args:
            agent_id: Agent 唯一 ID
            repository_url: 要 clone 的 Git Repository
            language: Sandbox Runtime 语言，默认 Python

        Returns:
            已启动的 Daytona Sandbox 实例
        """
        # 同一 manager 内优先复用 agent_id 对应的 Sandbox。
        if agent_id in self._active_sandboxes:
            sandbox = self._active_sandboxes[agent_id]
            # 正在运行时直接复用，避免重复创建远程 Runtime。
            if sandbox.state == "STARTED":
                return sandbox
            # 已停止但未删除时重新启动。
            sandbox.start()
            return sandbox

        # 没有缓存实例时创建新 Sandbox，并在创建阶段 clone Repository。
        sandbox = self.client.create_sandbox(
            agent_id=agent_id,
            repository_url=repository_url,
            branch=branch,
            language=language,
        )

        self._active_sandboxes[agent_id] = sandbox
        return sandbox

    def release(self, agent_id: str) -> None:
        """从活动表移除并删除 Agent 的 Sandbox。

        Args:
            agent_id: Agent ID
        """
        if agent_id in self._active_sandboxes:
            sandbox = self._active_sandboxes.pop(agent_id)
            try:
                sandbox.delete()
            except Exception as e:
                # 清理失败只记录日志，避免覆盖主任务的真实执行结果。
                print(f"Error deleting sandbox {agent_id}: {e}")

    def get(self, agent_id: str):
        """读取 Agent 当前缓存的 Sandbox。

        Args:
            agent_id: Agent ID

        Returns:
            Daytona Sandbox 实例；不存在时返回 None
        """
        return self._active_sandboxes.get(agent_id)

    def stop(self, agent_id: str) -> None:
        """停止但不删除 Sandbox，以便后续恢复并节省运行成本。

        Args:
            agent_id: Agent ID
        """
        if agent_id in self._active_sandboxes:
            sandbox = self._active_sandboxes[agent_id]
            try:
                sandbox.stop()
            except Exception as e:
                print(f"Error stopping sandbox {agent_id}: {e}")

    def list_active(self) -> list[str]:
        """列出当前 manager 持有 Sandbox 的全部 Agent ID。

        Returns:
            Agent ID 列表
        """
        return list(self._active_sandboxes.keys())
