"""Coding Agent Evaluation Dataset 定义。"""

from pydantic import BaseModel


class EvaluationCase(BaseModel):
    """一个可重复执行的 Coding Agent 评测任务。"""

    case_id: str

    repository: str = "mock_workspace"

    issue_number: int

    issue_title: str

    issue_body: str

    custom_instructions: str = ""

    base_branch: str = "main"

    scenario: str = "success"

    expected_min_retries: int = 0

    # -------------------------
    # 期望结果
    #
    # 当前阶段只评估我们已经真实存在的：
    # Workflow / Tester / Reviewer
    # -------------------------

    expected_success: bool = True

    expected_tests_passed: bool = True

    expected_review_verdict: str | None = "APPROVE"\

    expected_failure_reason: str | None = None

class RealLLMEvaluationCase(EvaluationCase):
    """使用真实 LLM 执行的 Coding Agent 评测任务。

    与 Mock Evaluation 的区别：
    - 不依赖 scenario 控制模型行为；
    - Coder 和 Reviewer 都使用真实 LLM；
    - retry 是否发生，由真实执行结果决定。

    """

    # 指定该 Case 使用哪套 MockSandbox 初始仓库。
    sandbox_fixture: str = "login_500"

    scenario: str = "real"



EVALUATION_CASES = [
    EvaluationCase(
        case_id="login_success",
        scenario="success",
        issue_number=1,
        issue_title="修复登录接口500错误",
        issue_body="登录接口存在bug",
        expected_success=True,
        expected_tests_passed=True,
        expected_review_verdict="APPROVE",
        expected_min_retries=0,
    ),
    EvaluationCase(
        case_id="review_reject_once",
        scenario="review_reject_once",
        issue_number=2,
        issue_title="修复登录接口并处理 Review 意见",
        issue_body="代码修改后需要经过 Reviewer 审查",
        expected_success=True,
        expected_tests_passed=True,
        expected_review_verdict="APPROVE",
        # 第一次 REQUEST_CHANGES，
        # Supervisor 应该至少触发一次重试。
        expected_min_retries=1,
    ),
    EvaluationCase(
        case_id="test_fail_once",
        scenario="test_fail_once",
        issue_number=3,
        issue_title="修复登录测试失败",
        issue_body=("登录接口返回的用户名字段不正确，需要修复并通过测试"),
        expected_success=True,
        expected_tests_passed=True,
        expected_review_verdict="APPROVE",
        expected_min_retries=1,
    ),
    EvaluationCase(
        case_id="test_fail_always",
        scenario="test_fail_always",
        issue_number=4,
        issue_title="模拟无法修复的登录测试失败",
        issue_body=("模拟 Coding Agent 多次修改后仍然无法通过测试"),
        expected_success=False,
        expected_tests_passed=False,
        # Tester 一直失败，因此不会进入 Reviewer。
        expected_review_verdict=None,
        # Supervisor max_retry = 3。
        expected_min_retries=3,
        expected_failure_reason=("max retry reached after test failure"),
    ),
]


REAL_LLM_EVALUATION_CASES = [
    RealLLMEvaluationCase(
    case_id="real_login_500_fix",
    sandbox_fixture="login_500",
    issue_number=101,
    issue_title="修复登录接口500错误",
    issue_body=(
        "使用正确账号 admin / 123456 登录时，接口会返回 500。"
        "请定位问题并修复，确保现有测试通过。"
    ),
    expected_success=True,
    expected_tests_passed=True,
    expected_review_verdict="APPROVE",
    expected_min_retries=0,
  ),
  RealLLMEvaluationCase(
    case_id="real_empty_average_fix",
    sandbox_fixture="empty_average",
    issue_number=102,
    issue_title="修复空列表计算平均值时的崩溃问题",
    issue_body=(
        "calculate_average() 在传入空列表时会发生异常。"
        "请修复该边界条件：空列表应返回 0，"
        "同时保持正常数字列表的计算结果不变，并确保测试通过。"
    ),
    expected_success=True,
    expected_tests_passed=True,
    expected_review_verdict="APPROVE",
    expected_min_retries=0,
),
]
