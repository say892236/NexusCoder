"""测试 Coder Retry Feedback Prompt。"""

from app.agents.prompts.coder_prompt import (
    build_coder_prompt,
)


def test_review_feedback_is_added_to_retry_prompt():
    """Reviewer 驳回后，Coder 应收到上一轮 Review Feedback。"""

    _, user_message = build_coder_prompt(
        repository="mock_workspace",
        issue_number=1,
        issue_title="修复登录接口",
        issue_body="登录接口存在问题",
        retry_count=1,
        review_result={
            "verdict": "REQUEST_CHANGES",
            "summary": "需要补充异常处理",
            "overall_severity": "medium",
        },
    )

    assert "## Retry Context" in user_message
    assert "retry attempt #1" in user_message

    assert "### Previous Review Feedback" in user_message
    assert "REQUEST_CHANGES" in user_message
    assert "需要补充异常处理" in user_message
    assert "medium" in user_message


def test_test_failure_is_added_to_retry_prompt():
    """Tester 失败后，Coder 应收到 pytest 失败信息。"""

    _, user_message = build_coder_prompt(
        repository="mock_workspace",
        issue_number=2,
        issue_title="修复测试失败",
        issue_body="当前实现导致单元测试失败",
        retry_count=1,
        test_result={
            "passed": False,
            "output": (
                "FAILED test_login.py::test_login\nAssertionError: expected 200 but got 500"
            ),
        },
    )

    assert "## Retry Context" in user_message
    assert "### Previous Test Failure" in user_message

    assert "FAILED test_login.py::test_login" in user_message
    assert "expected 200 but got 500" in user_message


def test_first_coder_run_has_no_retry_context():
    """第一次执行 Coder 时不应该出现 Retry Feedback。"""

    _, user_message = build_coder_prompt(
        repository="mock_workspace",
        issue_number=3,
        issue_title="普通 Issue",
        issue_body="修复一个普通问题",
        retry_count=0,
    )

    assert "## Retry Context" not in user_message
    assert "Previous Review Feedback" not in user_message
    assert "Previous Test Failure" not in user_message
