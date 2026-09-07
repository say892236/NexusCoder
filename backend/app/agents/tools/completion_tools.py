"""Agent 用来显式发出任务完成信号的 Completion Tool。

这些 Tool 不操作 Sandbox；它们把最终结果封装为 ``metadata.type=completion``，
BaseAgent 识别后停止 AgentLoop，并把 ``data`` 作为结构化执行结果交给外层任务。
"""

from app.agents.tools.base import BaseTool, ToolDefinition, ToolResult


class FinishReviewTool(BaseTool):
    """通知 AgentLoop：Code Review 已完成。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="finish_review",
            description="Complete the code review and return final summary/verdict. Call this after posting all the findings. This will signal the end of the review process, so only call this once you're done reviewing and posting findings.",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Short final summary of the review and main issues detected",
                    },
                    "verdict": {
                        "type": "string",
                        "enum": ["APPROVE", "REQUEST_CHANGES", "COMMENT"],
                        "description": "Final review verdict for the pull request",
                    },
                    "overall_severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Overall severity level across findings",
                    },
                },
                "required": ["summary", "verdict"],
            },
        )

    async def execute(
        self, summary: str, verdict: str, overall_severity: str = "medium", **kwargs
    ) -> ToolResult:
        """校验并返回 Review 的最终结构化结论。

        Args:
            summary: 最终简短审查摘要
            verdict: 最终 PR 结论
            overall_severity: 全局问题严重级别

        Returns:
            包含 Review 数据与完成信号的 ToolResult
        """
        normalized_verdict = verdict.strip().upper()
        if normalized_verdict not in {"APPROVE", "REQUEST_CHANGES", "COMMENT"}:
            return ToolResult(
                success=False,
                error=f"Invalid verdict '{verdict}'. Use APPROVE, REQUEST_CHANGES, or COMMENT.",
            )

        normalized_severity = overall_severity.strip().lower()
        if normalized_severity not in {"low", "medium", "high", "critical"}:
            return ToolResult(
                success=False,
                error=f"Invalid overall_severity '{overall_severity}'. Use low, medium, high, or critical.",
            )

        return ToolResult(
            success=True,
            data={
                "summary": summary,
                "verdict": normalized_verdict,
                "overall_severity": normalized_severity,
                "completed": True,
            },
            metadata={"type": "completion"},
        )


class FinishTaskTool(BaseTool):
    """通知 AgentLoop：Coding 任务已完成并准备创建 PR。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="finish_task",
            description="Complete the coding task. Call this after you've implemented changes, tested them, and pushed to a branch.",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Summary of what was implemented",
                    },
                    "branch_name": {
                        "type": "string",
                        "description": "Name of the branch with changes",
                    },
                },
                "required": ["summary", "branch_name"],
            },
        )

    async def execute(
        self,
        summary: str,
        branch_name: str,
        files_changed: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        """校验并返回 Coding 任务的最终结构化结果。

        Args:
            summary: 实现摘要
            branch_name: 承载变更的 Branch
            files_changed: 修改文件列表

        Returns:
            包含任务数据与完成信号的 ToolResult
        """
        result = self.sandbox.process.exec(
            command=(
                "git diff "
                "main...HEAD "
                "--name-only"
            ),
            cwd="workspace/repo",
            timeout=30,
        )

        files_changed = []

        if result.exit_code == 0:
            files_changed = [
                line.strip()
                for line in result.result.splitlines()
                if line.strip()
            ]

        return ToolResult(
            success=True,
            data={
                "summary": summary,
                "branch_name": branch_name,
                "files_changed": files_changed,
                "completed": True,
            },
            metadata={
                "type": "completion"
            },
        )


class FinishSummaryTool(BaseTool):
    """通知 AgentLoop：PR summary 已生成。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="finish_summary",
            description="Complete summary generation for the pull request description update.",
            parameters={
                "type": "object",
                "properties": {
                    "summary_text": {
                        "type": "string",
                        "description": "Final PR summary markdown text.",
                    },
                    "pr_title": {
                        "type": "string",
                        "description": "AI-generated replacement title for the pull request.",
                    },
                },
                "required": ["summary_text", "pr_title"],
            },
        )

    async def execute(
        self,
        summary_text: str,
        pr_title: str,
        **kwargs,
    ) -> ToolResult:
        """校验并返回最终 PR summary 与标题。"""
        cleaned_summary = summary_text.strip()
        if not cleaned_summary:
            return ToolResult(
                success=False,
                error="summary_text must not be empty.",
            )
        cleaned_title = pr_title.strip()
        if not cleaned_title:
            return ToolResult(
                success=False,
                error="pr_title must not be empty.",
            )

        return ToolResult(
            success=True,
            data={
                "summary_text": cleaned_summary,
                "pr_title": cleaned_title,
                "completed": True,
            },
            metadata={"type": "completion"},
        )
