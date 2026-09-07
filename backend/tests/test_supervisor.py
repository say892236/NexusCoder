from app.agents.multi_agent.supervisor import supervisor_node


def test_supervisor_stops_when_test_retry_reaches_limit():
    state = {
        "current_agent": "tester",
        "next_agent": "tester",
        "retry_count": 2,

        "code_result": {
            "completed": True,
        },

        "test_result": {
            "passed": False,
            "output": "pytest failed",
        },

        "review_result": {},
    }

    result = supervisor_node(state)

    assert result["retry_count"] == 3
    assert result["next_agent"] == "finish"
    assert result["final_result"]["success"] is False



def test_supervisor_stops_when_review_retry_reaches_limit():
    state = {
        "current_agent": "reviewer",
        "next_agent": "reviewer",
        "retry_count": 2,

        "code_result": {
            "completed": True,
        },

        "test_result": {
            "passed": True,
        },

        "review_result": {
            "verdict": "REQUEST_CHANGES",
            "summary": "发现代码问题",
            "completed": True,
        },
    }

    result = supervisor_node(state)

    assert result["retry_count"] == 3
    assert result["next_agent"] == "finish"
    assert result["final_result"]["success"] is False


def test_supervisor_finishes_when_review_approved():
    state = {
        "current_agent": "reviewer",
        "next_agent": "reviewer",
        "retry_count": 0,

        "code_result": {
            "completed": True,
        },

        "test_result": {
            "passed": True,
        },

        "review_result": {
            "verdict": "APPROVE",
            "summary": "代码检查通过",
            "completed": True,
        },
    }

    result = supervisor_node(state)

    assert result["next_agent"] == "finish"
    assert result["retry_count"] == 0
    assert result["final_result"]["success"] is True
    assert result["final_result"]["review_result"]["verdict"] == "APPROVE"


def test_supervisor_stops_when_coder_runtime_failed():
    state = {
        "current_agent": "coder",
        "next_agent": "coder",
        "retry_count": 0,

        "coder_status": "failed",
        "coder_error": "LLM API timeout",

        "code_result": {},
        "test_result": {},
        "review_result": {},
    }

    result = supervisor_node(state)

    assert result["next_agent"] == "finish"
    assert result["final_result"]["success"] is False
    assert result["final_result"]["reason"] == "coder runtime failed"
    assert result["final_result"]["error"] == "LLM API timeout"

def test_supervisor_stops_when_reviewer_runtime_failed():
    state = {
        "current_agent": "reviewer",
        "next_agent": "reviewer",
        "retry_count": 0,

        "reviewer_status": "failed",
        "reviewer_error": "agent_loop_timeout",

        "code_result": {
            "completed": True,
        },

        "test_result": {
            "passed": True,
        },

        "review_result": {
            "completed": False,
            "verdict": "REQUEST_CHANGES",
        },
    }

    result = supervisor_node(state)

    assert result["next_agent"] == "finish"
    assert result["final_result"]["success"] is False
    assert result["final_result"]["reason"] == "reviewer runtime failed"
    assert result["final_result"]["error"] == "agent_loop_timeout"
