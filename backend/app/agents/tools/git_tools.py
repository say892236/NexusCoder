"""通过 Daytona SDK 执行 Repository Git 工作流的 Tool。"""

import json

from app.agents.tools.base import BaseTool, ToolDefinition, ToolResult


class GitStatusTool(BaseTool):
    """读取 Repository 的 Git 状态。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_status",
            description="Get the current status of the Git repository (branch, modified files, commits ahead/behind)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.status()`` 执行 Git status。"""
        try:
            status = self.sandbox.git.status(path)

            return ToolResult(
                success=True,
                data={
                    "current_branch": status.current_branch,
                    "ahead": status.ahead,
                    "behind": status.behind,
                    "modified_files": [f.name for f in status.file_status],
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitCreateBranchTool(BaseTool):
    """创建新的 Git Branch。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_create_branch",
            description="Create a new Git branch",
            parameters={
                "type": "object",
                "properties": {
                    "branch_name": {
                        "type": "string",
                        "description": "Name of the new branch",
                    },
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    },
                },
                "required": ["branch_name"],
            },
        )

    async def execute(self, branch_name: str, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.create_branch()`` 创建 Branch。"""
        try:
            self.sandbox.git.create_branch(path, branch_name)
            return ToolResult(success=True, data={"branch": branch_name})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitCheckoutBranchTool(BaseTool):
    """切换到指定 Git Branch。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_checkout_branch",
            description="Switch to a different Git branch",
            parameters={
                "type": "object",
                "properties": {
                    "branch_name": {
                        "type": "string",
                        "description": "Name of branch to checkout",
                    },
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    },
                },
                "required": ["branch_name"],
            },
        )

    async def execute(self, branch_name: str, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.checkout_branch()`` 执行 checkout。"""
        try:
            self.sandbox.git.checkout_branch(path, branch_name)
            return ToolResult(success=True, data={"branch": branch_name})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitAddTool(BaseTool):
    """把文件加入 Git 暂存区，为 Commit 做准备。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_add",
            description="Stage files for commit (git add)",
            parameters={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files to stage (use ['.'] for all changes)",
                    },
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    },
                },
                "required": ["files"],
            },
        )

    async def execute(self, files: list[str], path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.add()`` 执行暂存。"""
        try:
            self.sandbox.git.add(path, files)
            return ToolResult(success=True, data={"staged_files": files})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitCommitTool(BaseTool):
    """将暂存区变更创建为 Commit。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_commit",
            description="Commit staged changes with a message",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Commit message"},
                    "author_name": {
                        "type": "string",
                        "description": "Author name (optional). If omitted, uses git config identity.",
                    },
                    "author_email": {
                        "type": "string",
                        "description": "Author email (optional). If omitted, uses git config identity.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    },
                },
                "required": ["message"],
            },
        )

    async def execute(
        self,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
        path: str = "workspace/repo",
        **kwargs,
    ) -> ToolResult:
        """默认沿用 Repository Git 身份，仅在显式传参时覆盖后执行 Commit。"""
        try:
            normalized_name = (author_name or "").strip()
            normalized_email = (author_email or "").strip()
            if normalized_name and normalized_email:
                self.sandbox.git.commit(path, message, normalized_name, normalized_email)
                return ToolResult(
                    success=True,
                    data={
                        "message": message,
                        "author": f"{normalized_name} <{normalized_email}>",
                    },
                )

        # 默认沿用编排层预先配置的 Git 身份，避免无意覆盖作者元数据。
            response = self.sandbox.process.exec(
                command=f"git commit -m {json.dumps(message)}",
                cwd=path,
                timeout=30,
            )
            return ToolResult(
                success=response.exit_code == 0,
                data={
                    "message": message,
                    "author": "git-config",
                    "stdout": response.result,
                    "exit_code": response.exit_code,
                },
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitPushTool(BaseTool):
    """把本地 Commit 推送到远端 Repository。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_push",
            description="Push committed changes to remote repository",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.push()`` 执行 push。"""
        try:
            self.sandbox.git.push(path)
            return ToolResult(success=True, data={"pushed": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitPullTool(BaseTool):
    """从远端 Repository 拉取变更。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_pull",
            description="Pull latest changes from remote repository",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.pull()`` 执行 pull。"""
        try:
            self.sandbox.git.pull(path)
            return ToolResult(success=True, data={"pulled": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GitBranchesTool(BaseTool):
    """列出全部 Git Branch。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="git_branches",
            description="List all branches in the repository",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repository path (default: workspace/repo)",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona git.branches()`` 获取 Branch 列表。"""
        try:
            response = self.sandbox.git.branches(path)
            return ToolResult(
                success=True,
                data={"branches": response.branches},
                metadata={"count": len(response.branches)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
