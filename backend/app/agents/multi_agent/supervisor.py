from app.agents.multi_agent.state import CodingAgentState


def supervisor_node(state: CodingAgentState):
    print("DEBUG supervisor:", {
        "current_agent": state.get("current_agent"),
        "next_agent": state.get("next_agent"),
        "retry_count": state.get("retry_count"),
        "code_result": state.get("code_result"),
        "test_result": state.get("test_result"),
        "review_result": state.get("review_result"),
    })

    current_agent = state.get("current_agent")
    retry_count = state.get("retry_count", 0)

    max_retry = 3

    # 第一次进入流程：先执行 Coder
    if not current_agent:
        return {
            "next_agent": "coder",
            "retry_count": retry_count,
        }

    # Coder 完成后进入 Tester
    if current_agent == "coder":
        coder_status = state.get("coder_status")
        code_result = state.get("code_result", {})

        # Coder Runtime 本身失败
        if coder_status == "failed":
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": False,
                    "reason": "coder runtime failed",
                    "error": state.get("coder_error"),
                    "code_result": code_result,
                },
            }

        # Coder 必须真正完成任务，才能进入 Tester
        if not code_result.get("completed"):
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": False,
                    "reason": "coder did not complete task",
                    "code_result": code_result,
                },
            }

        return {
            "next_agent": "tester",
            "retry_count": retry_count,
        }

    # Tester 根据测试结果决定进入 Reviewer 或重新 Coder
    if current_agent == "tester":
        test_result = state.get("test_result", {})

        if test_result.get("passed"):
            return {
                "next_agent": "reviewer",
                "retry_count": retry_count,
            }

        # 测试失败，先增加重试次数
        retry_count += 1

        # 达到上限后立即结束，不再多跑一次 Coder
        if retry_count >= max_retry:
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": False,
                    "reason": "max retry reached after test failure",
                    "code_result": state.get("code_result", {}),
                    "test_result": test_result,
                    "review_result": state.get("review_result", {}),
                },
            }

        return {
            "next_agent": "coder",
            "retry_count": retry_count,
        }

    # Reviewer 根据审查结果决定完成或重新修改
    if current_agent == "reviewer":
        review_result = state.get("review_result", {})
        reviewer_status = state.get("reviewer_status")

        if reviewer_status == "failed":
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": False,
                    "reason": "reviewer runtime failed",
                    "error": state.get("reviewer_error"),
                    "code_result": state.get("code_result", {}),
                    "test_result": state.get("test_result", {}),
                    "review_result": review_result,
                },
            }

        approved = (
            review_result.get("approved") is True
            or str(
                review_result.get("verdict", "")
            ).upper() == "APPROVE"
        )

        # 审查通过：正式生成成功结果
        if approved:
            # HITL 开启时，Reviewer 通过后还需要人工确认。
            if state.get("require_human_approval", False):
                return {
                    "next_agent": "human_approval",
                    "retry_count": retry_count,
                }

            # 没开启 HITL 时保持原来的行为。
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": True,
                    "code_result": state.get("code_result", {}),
                    "test_result": state.get("test_result", {}),
                    "review_result": review_result,
                },
            }
        # 审查未通过，也算一次重试
        retry_count += 1

        if retry_count >= max_retry:
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": False,
                    "reason": "max retry reached after review rejection",
                    "code_result": state.get("code_result", {}),
                    "test_result": state.get("test_result", {}),
                    "review_result": review_result,
                },
            }

        return {
            "next_agent": "coder",
            "retry_count": retry_count,
        }

    # =========================================================
    # Human Approval
    # =========================================================

    if current_agent == "human_approval":
        human_approved = state.get("human_approved") is True

        # 人工批准
        if human_approved:
            return {
                "next_agent": "finish",
                "retry_count": retry_count,
                "final_result": {
                    "success": True,
                    "code_result": state.get("code_result", {}),
                    "test_result": state.get("test_result", {}),
                    "review_result": state.get("review_result", {}),
                    "human_approved": True,
                },
            }

        # 人工拒绝
        return {
            "next_agent": "finish",
            "retry_count": retry_count,
            "final_result": {
                "success": False,
                "reason": "human rejected",
                "code_result": state.get("code_result", {}),
                "test_result": state.get("test_result", {}),
                "review_result": state.get("review_result", {}),
                "human_approved": False,
            },
        }

    # 非预期状态兜底
    return {
        "next_agent": "finish",
        "retry_count": retry_count,
        "final_result": {
            "success": False,
            "reason": f"unknown current_agent: {current_agent}",
        },
    }
