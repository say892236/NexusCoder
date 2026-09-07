from typing import (
    NotRequired,
    Required,
    TypedDict,
)


class AgentUsage(TypedDict):
    """一个 Agent 在当前 Workflow 中的累计 Token 使用情况。"""

    runs: int

    tokens_used: int
    prompt_tokens: int
    completion_tokens: int

    cache_hit_tokens: int
    cache_miss_tokens: int


class CodingAgentState(TypedDict):
    """
    Multi-Agent 工作流共享状态。

    State 中只保存：
    1. 任务输入
    2. 工作流状态
    3. Agent 结果
    4. 可持久化执行轨迹

    Sandbox / LLM Client 等运行时对象放入 Runtime Context。
    """

    # =========================
    # 任务基础信息
    # =========================

    repository: Required[str]
    issue_number: Required[int]
    issue_title: Required[str]
    issue_body: Required[str]

    custom_instructions: NotRequired[str]
    base_branch: NotRequired[str]

    # =========================
    # LangGraph 路由状态
    # =========================

    current_agent: NotRequired[str]
    next_agent: NotRequired[str]

    retry_count: NotRequired[int]

    # =========================
    # 各节点业务结果
    # =========================

    code_result: NotRequired[dict]
    test_result: NotRequired[dict]
    review_result: NotRequired[dict]

    final_result: NotRequired[dict]

    # =========================
    # Agent Runtime 执行结果
    # =========================

    coder_status: NotRequired[str]
    coder_error: NotRequired[str | None]

    reviewer_status: NotRequired[str]
    reviewer_error: NotRequired[str | None]

        # =========================
    # Agent Trace
    # =========================

    # 只保存最近一次运行的完整 Trace，
    # 主要用于调试和 LangSmith / 本地日志查看。
    coder_trace: NotRequired[dict]
    reviewer_trace: NotRequired[dict]

    # =========================
    # Agent Usage
    # =========================

    # 保存整个 Workflow 生命周期中的累计 Token 数据。
    #
    # 如果因为 Tester / Reviewer 触发 Retry，
    # 后续 Coder / Reviewer 的 Token 会继续累加，
    # 而不是覆盖前一次运行的数据。
    coder_usage: NotRequired[AgentUsage]
    reviewer_usage: NotRequired[AgentUsage]

    # =========================
    # Reviewer 配置
    # =========================

    review_sensitivity: NotRequired[str]
    review_custom_instructions: NotRequired[str]
    review_ignore_patterns: NotRequired[list[str]]

    # =========================
    # HITL
    # =========================

    human_approved: NotRequired[bool]

    # 是否要求人工审批。
    require_human_approval: NotRequired[bool]

    #召回历史经验
    recalled_memories: NotRequired[list[dict[str, object]]]
