"""按 Agent 类型组织和调度 Tool。

Tool Calling 的连接点：ToolManager 把已注册 Tool 转成 OpenAI function schema 提供给 LLM，
再按模型返回的 name/arguments 找到具体 Tool；同一轮的多个 Tool call 通过
``execute_batch()`` 并发执行，并按 call ID 把 ToolResult 交还 BaseAgent。
"""

from app.agents.tools.base import BaseTool, ToolResult
from app.agents.tools.completion_tools import (
    FinishReviewTool,
    FinishSummaryTool,
    FinishTaskTool,
)
from app.agents.tools.file_tools import (
    CreateFileTool,
    DeleteFileTool,
    ListFilesTool,
    ReadFileTool,
    ReplaceInFilesTool,
    SearchFilesTool,
)
from app.agents.tools.git_tools import (
    GitAddTool,
    GitBranchesTool,
    GitCheckoutBranchTool,
    GitCommitTool,
    GitCreateBranchTool,
    GitPullTool,
    GitPushTool,
    GitStatusTool,
)
from app.agents.tools.process_tools import (
    RunCodeTool,
    RunCommandTool,
    RunLinterTool,
    RunTestsTool,
)
from app.agents.tools.review_posting_tools import (
    PostFileReviewFindingTool,
    PostInlineReviewFindingTool,
)
from app.db.base import AsyncSessionLocal
from app.services.github import GitHubService


class ToolManager:
    """维护 Tool 注册表，并负责 schema 暴露与调用分发。"""

    def __init__(self, sandbox):
        """使用 Daytona Sandbox 初始化 ToolManager。

        Args:
            sandbox: 所有 Sandbox Tool 共用的 Daytona Sandbox 实例
        """
        self.sandbox = sandbox
        self._tools: dict[str, BaseTool] = {}

    def register_tools(self, tool_classes: list[type[BaseTool]]) -> None:
        """实例化并注册一组 Tool 类。

        Args:
            tool_classes: 要实例化和注册的 BaseTool 子类列表
        """
        for tool_class in tool_classes:
            tool = tool_class(self.sandbox)
            self._tools[tool.definition.name] = tool

    def register_tool_instances(self, tools: list[BaseTool]) -> None:
        """注册已构造好的 Tool 实例，用于需要额外依赖的 Tool。"""
        for tool in tools:
            self._tools[tool.definition.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        """按 function name 查找 Tool。

        Args:
            name: Tool 名称

        Returns:
            BaseTool 实例；未注册时返回 None
        """
        return self._tools.get(name)

    def get_all_schemas(self) -> list[dict]:
        """返回所有 Tool 的 OpenAI function calling schema。

        Returns:
            OpenAI 格式的 Tool schema 列表
        """
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def list_tool_names(self) -> list[str]:
        """列出全部已注册 Tool 名称。

        Returns:
            Tool 名称列表
        """
        return list(self._tools.keys())

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """根据 LLM 给出的名称和参数执行单个 Tool。

        Args:
            tool_name: 要执行的 Tool 名称
            **kwargs: Tool 的结构化参数

        Returns:
            ToolResult
        """
        tool = self.get_tool(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Tool not found: {tool_name}")

        return await tool.execute(**kwargs)

    async def execute_batch(self, tool_calls: list[dict]) -> dict[str, ToolResult]:
        """并发执行同一轮 LLM 响应中的多个 Tool call。

        Args:
            tool_calls: 包含 ``id``、``name``、``arguments`` 的调用字典列表

        Returns:
            Tool call ID 到 ToolResult 的映射
        """
        import asyncio

        async def execute_one(call: dict):
            result = await self.execute(call["name"], **call["arguments"])
            return call["id"], result

        # 保留 call ID，使并发完成后仍能把结果对应回原始 tool_calls。
        tasks = [execute_one(call) for call in tool_calls]
        completed = await asyncio.gather(*tasks)

        return {call_id: result for call_id, result in completed}


# 不同 Agent 使用最小必要 Tool 集，降低误操作面并让 Prompt 能力边界更清晰。


def get_reviewer_tools(
    sandbox,
    review_id: str,
    installation_token: str,
    owner: str,
    repo: str,
    pr_number: int,
    commit_sha: str,
) -> ToolManager:
    """组装 Code Review Agent 的 Tool 集。

    重点：只读文件操作，加上测试和 lint 验证能力。

    Tool：
    - File：读取、列目录、搜索
    - Git：查看状态和 Branch
    - Process：运行测试、lint 和命令
    - Completion：finish_review

    Args:
        sandbox: Daytona Sandbox 实例

    Returns:
        注册了 Review 专用 Tool 的 ToolManager
    """
    manager = ToolManager(sandbox)
    manager.register_tools(
        [
            # File：只读操作。
            ReadFileTool,
            ListFilesTool,
            SearchFilesTool,
            # Git：只观察状态。
            GitStatusTool,
            GitBranchesTool,
            # Process：用于验证，不直接修改代码。
            RunTestsTool,
            RunLinterTool,
            RunCommandTool,
            # Completion：显式告诉 AgentLoop 审查已完成。
            FinishReviewTool,
        ]
    )
    github = GitHubService()
    manager.register_tool_instances(
        [
            PostInlineReviewFindingTool(
                sandbox=sandbox,
                github_service=github,
                session_factory=AsyncSessionLocal,
                review_id=review_id,
                installation_token=installation_token,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                commit_sha=commit_sha,
            ),
            PostFileReviewFindingTool(
                sandbox=sandbox,
                github_service=github,
                session_factory=AsyncSessionLocal,
                review_id=review_id,
                installation_token=installation_token,
                owner=owner,
                repo=repo,
                pr_number=pr_number,
                commit_sha=commit_sha,
            ),
        ]
    )
    return manager


def get_coder_tools(sandbox) -> ToolManager:
    """组装后台 Coding Agent（Issue -> PR）的 Tool 集。

    重点：完整文件 CRUD 与创建 PR 前的 Git 工作流。

    Tool：
    - File：读取、列目录、搜索、替换、创建、删除
    - Git：Branch、checkout、add、Commit、push 的完整流程
    - Process：运行代码、测试、lint 和命令
    - Completion：finish_task

    Args:
        sandbox: Daytona Sandbox 实例

    Returns:
        注册了 Coding 专用 Tool 的 ToolManager
    """
    manager = ToolManager(sandbox)
    manager.register_tools(
        [
            # File：Coding Agent 需要完整 CRUD。
            ReadFileTool,
            ListFilesTool,
            SearchFilesTool,
            ReplaceInFilesTool,
            CreateFileTool,
            DeleteFileTool,
            # Git：从创建 Branch 到 push 的完整工作流。
            GitStatusTool,
            GitBranchesTool,
            GitCreateBranchTool,
            GitCheckoutBranchTool,
            GitAddTool,
            GitCommitTool,
            GitPushTool,
            GitPullTool,
            # Process：开发与验证命令。
            RunCodeTool,
            RunTestsTool,
            RunLinterTool,
            RunCommandTool,
            # Completion：返回 summary、Branch 和变更文件。
            FinishTaskTool,
        ]
    )
    return manager


def get_summary_tools(sandbox) -> ToolManager:
    """组装 Summary Agent 的最小 Tool 集。

    重点：只提供理解变更所需的最小只读能力。

    Tool：
    - File：读取、列目录、搜索
    - Git：查看状态

    Args:
        sandbox: Daytona Sandbox 实例

    Returns:
        注册了 Summary 专用 Tool 的 ToolManager
    """
    manager = ToolManager(sandbox)
    manager.register_tools(
        [
            # File：最小只读操作。
            ReadFileTool,
            ListFilesTool,
            SearchFilesTool,
            # Git：只查看状态。
            GitStatusTool,
            # Completion：返回 PR summary。
            FinishSummaryTool,
        ]
    )
    return manager
