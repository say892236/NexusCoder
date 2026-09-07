from typing import NotRequired, TypedDict


class MultiAgentRuntimeContext(TypedDict):
    """
    Multi-Agent 单次运行需要的外部依赖。

    这些对象属于 Runtime，
    不应该进入可持久化的 LangGraph State。
    """

    # Coder / Tester / Reviewer 共用的执行环境。
    sandbox: NotRequired[object]

    # Coder / Reviewer 使用的 LLM Client。
    llm_client: NotRequired[object]
