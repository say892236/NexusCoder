from langgraph.types import interrupt

from app.agents.multi_agent.state import CodingAgentState


async def human_approval_node(
    state: CodingAgentState,
):
    """
    在自动测试和 Reviewer 审查完成后，
    暂停 Graph，等待人工 Approve / Reject。
    """

    approved = interrupt(
        {
            "type": "human_approval",
            "message": "代码修改和自动评审已完成，是否批准继续？",
            "repository": state["repository"],
            "issue_number": state["issue_number"],
            "code_result": state.get("code_result", {}),
            "test_result": state.get("test_result", {}),
            "review_result": state.get("review_result", {}),
        }
    )

    return {
        "current_agent": "human_approval",
        "human_approved": approved is True,
    }
