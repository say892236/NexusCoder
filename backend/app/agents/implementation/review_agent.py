"""Code Review Agent 实现。"""

from app.agents.base import BaseAgent
from app.agents.prompts.reviewer_prompt import build_reviewer_prompt


class ReviewAgent(BaseAgent):
    """自主分析 PR diff 并发布审查结论的 Agent。"""

    def __init__(
        self,
        agent_id: str,
        pr_title: str,
        pr_description: str,
        pr_diff: str,
        sensitivity: str,
        custom_instructions: str,
        ignore_patterns: list[str],
        tools,
        llm_client,
        **kwargs,
    ):
        """使用 PR 上下文、审查配置和 Tool 初始化 Review Agent。

        Args:
            agent_id: Agent 唯一 ID
            pr_title: PR 标题
            pr_description: PR 描述
            pr_diff: PR diff
            sensitivity: 审查敏感度（LOW、MEDIUM、HIGH）
            custom_instructions: 用户自定义指令
            ignore_patterns: 要忽略的文件模式
            tools: 注册了 Review Tool 的 ToolManager
            llm_client: OpenAI 客户端
            **kwargs: 传给 BaseAgent 的预算等附加参数
        """
        # system Prompt 定义审查标准、输出约束和 Tool 使用方式。
        system_prompt = build_reviewer_prompt(
            sensitivity=sensitivity,
            custom_instructions=custom_instructions,
            ignore_patterns=ignore_patterns,
        )

        # 首条用户消息提供本次 PR 的具体上下文和 diff。
        initial_user_message = f"""# Pull Request Review

**Title**: {pr_title}

**Description**:
{pr_description}

**Diff**:
```diff
{pr_diff}
```

---

Begin your code review. Use your tools to gather context, verify behavior, and analyze the changes thoroughly. When complete, call `finish_review()` with your review.
"""

        # 复用 BaseAgent 的 LLM/Tool Calling 循环。
        super().__init__(
            agent_id=agent_id,
            system_prompt=system_prompt,
            initial_user_message=initial_user_message,
            tools=tools,
            llm_client=llm_client,
            **kwargs,
        )
