"""后台 Coding Agent 实现（Issue -> PR）。

本类只负责把 Issue 上下文组装成 Prompt，并把通用能力交给 BaseAgent；具体文件、Git、
测试等操作由注入的 ToolManager 完成，Sandbox 与 PR 则由外层 Celery task 管理。
"""

from app.agents.base import BaseAgent
from app.agents.prompts.coder_prompt import build_coder_prompt


class BackgroundAgent(BaseAgent):
    """根据 GitHub Issue 自主修改 Repository 的 Coding Agent。"""

    def __init__(
        self,
        agent_id: str,
        repository: str,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        custom_instructions: str,
        tools,
        llm_client,
        recalled_memories: list[dict[str, object]] | None = None,
        retry_count: int = 0,
        test_result: dict | None = None,
        review_result: dict | None = None,
        **kwargs,
    ):
        """初始化后台 Coding Agent。

                Args:
                    agent_id: Agent 唯一 ID
                    repository: Repository 名称（owner/repo）
                    issue_number: GitHub Issue 编号
                    issue_title: Issue 标题
                    issue_body: Issue 描述
                    custom_instructions: 用户补充指令
                    tools: 已注册 Coding Tool 的 ToolManager
                    llm_client: OpenAI 客户端
                    recalled_memories: 当前任务召回出的历史 Repository Memory
                    retry_count: 当前 Multi-Agent Workflow 已发生的重试次数
                    test_result: 上一轮 Tester 执行结果
                    review_result: 上一轮 Reviewer 审查结果
                    **kwargs: 传给 BaseAgent 的预算等附加参数
        """
        # Prompt builder 分离稳定规则与当前 Issue 上下文。
        system_prompt, initial_user_message = build_coder_prompt(
            repository=repository,
            issue_number=issue_number,
            issue_title=issue_title,
            issue_body=issue_body,
            custom_instructions=custom_instructions,
            recalled_memories=recalled_memories,
            retry_count=retry_count,
            test_result=test_result,
            review_result=review_result,
        )

        # 通用的消息状态、LLM 调用与 Tool Calling 由 BaseAgent 初始化。
        super().__init__(
            agent_id=agent_id,
            system_prompt=system_prompt,
            initial_user_message=initial_user_message,
            tools=tools,
            llm_client=llm_client,
            **kwargs,
        )
