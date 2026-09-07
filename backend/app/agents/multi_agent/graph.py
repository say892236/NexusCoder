"""
Multi-Agent LangGraph 工作流。

负责：
1. 创建 Graph
2. 注册 Agent Node
3. 配置节点之间的流转关系
4. 编译成可执行 Agent Workflow

Sandbox / LLM 等运行时依赖通过 Runtime Context 注入，
不再进入 CodingAgentState。
"""

from langgraph.constants import START
from langgraph.graph import END, StateGraph

from app.agents.multi_agent.context import MultiAgentRuntimeContext
from app.agents.multi_agent.nodes.coder import coder_node
from app.agents.multi_agent.nodes.human_approval import (
    human_approval_node,
)
from app.agents.multi_agent.nodes.reviewer import reviewer_node
from app.agents.multi_agent.nodes.tester import tester_node
from app.agents.multi_agent.state import CodingAgentState
from app.agents.multi_agent.supervisor import supervisor_node



def route_next_agent(
    state: CodingAgentState,
) -> str:
    """根据 Supervisor 决策选择下一个节点。"""

    return state["next_agent"]



def build_graph(checkpointer=None):
    builder = StateGraph(
        state_schema=CodingAgentState,
        context_schema=MultiAgentRuntimeContext,
    )

    # =========================
    # 注册节点
    # =========================

    builder.add_node(
        "supervisor",
        supervisor_node,
    )

    builder.add_node(
        "coder",
        coder_node,
    )

    builder.add_node(
        "tester",
        tester_node,
    )

    builder.add_node(
        "reviewer",
        reviewer_node,
    )

    builder.add_node(
        "human_approval",
        human_approval_node,
    )

    # =========================
    # 工作流入口
    # =========================

    builder.add_edge(
        START,
        "supervisor",
    )

    # =========================
    # Supervisor 路由
    # =========================

    builder.add_conditional_edges(
    "supervisor",
    route_next_agent,
    {
        "coder": "coder",
        "tester": "tester",
        "reviewer": "reviewer",
        "human_approval": "human_approval",
        "finish": END,
    },
)
    # =========================
    # Worker -> Supervisor
    # =========================

    builder.add_edge(
        "coder",
        "supervisor",
    )

    builder.add_edge(
        "tester",
        "supervisor",
    )

    builder.add_edge(
        "reviewer",
        "supervisor",
    )


    builder.add_edge(
        "human_approval",
        "supervisor",
    )

    return builder.compile(
        checkpointer=checkpointer,
    )
