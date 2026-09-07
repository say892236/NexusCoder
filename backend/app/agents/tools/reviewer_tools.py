from app.agents.tools.base import (
    BaseTool,
    ToolDefinition,
    ToolResult,
)


class GitDiffTool(BaseTool):
    """获取当前工作分支相对于基础分支的完整代码 Diff。"""

    def __init__(
        self,
        sandbox,
        base_branch: str = "main",
    ):
        super().__init__(sandbox)

        self.base_branch = base_branch

    @property
    def definition(self):
        return ToolDefinition(
            name="git_diff",
            description=(
                "Show all code changes made by the "
                "current branch compared with the base branch"
            ),
            parameters={
                "type": "object",
                "properties": {},
            },
        )

    async def execute(self, **kwargs):
        result = self.sandbox.process.exec(
            command=(
                f"git diff "
                f"{self.base_branch}...HEAD"
            ),
            cwd="workspace/repo",
        )

        if result.exit_code != 0:
            return ToolResult(
                success=False,
                error=result.result,
            )

        return ToolResult(
            success=True,
            data={
                "diff": result.result,
            },
        )
