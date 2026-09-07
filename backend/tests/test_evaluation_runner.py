"""测试 Coding Agent Evaluation Runner。"""

from app.evaluation.cases import (
    EVALUATION_CASES,
)
from app.evaluation.runner import (
    run_evaluation_case,
    run_evaluation_dataset,
)


async def test_run_single_evaluation_case():
    """验证单个 Evaluation Case 可以正常执行。"""

    case = EVALUATION_CASES[0]

    result = await run_evaluation_case(case)

    assert result.case_id == "login_success"

    assert result.workflow_success is True
    assert result.tests_passed is True
    assert result.review_verdict == "APPROVE"

    assert result.workflow_match is True
    assert result.tests_match is True
    assert result.review_match is True

    assert result.case_passed is True


async def test_run_evaluation_dataset():
    """验证完整 Dataset 可以批量执行。"""

    result = await run_evaluation_dataset(EVALUATION_CASES)

    assert result.total_cases == 4


    assert result.passed_cases == 4
    assert result.failed_cases == 0
    assert result.pass_rate == 1.0

    assert len(result.results) == 4


async def test_review_reject_once_case():
    """Reviewer 第一次拒绝后，Workflow 应能重试并最终成功。"""

    case = next(case for case in EVALUATION_CASES if case.case_id == "review_reject_once")

    result = await run_evaluation_case(case)

    assert result.workflow_success is True
    assert result.tests_passed is True
    assert result.review_verdict == "APPROVE"

    # 关键：证明不是直接成功，
    # 中间真的发生过 Retry。
    assert result.retry_count >= 1
    assert result.retry_match is True

    assert result.case_passed is True


async def test_test_fail_once_case():
    """Tester 第一次失败后，Coder 应重试并最终修复。"""

    case = next(case for case in EVALUATION_CASES if case.case_id == "test_fail_once")

    result = await run_evaluation_case(case)

    assert result.workflow_success is True

    # 最终一次测试应该已经通过。
    assert result.tests_passed is True

    assert result.review_verdict == "APPROVE"

    # 证明中间发生过 Tester Failure Retry。
    assert result.retry_count >= 1
    assert result.retry_match is True

    assert result.failure_reason is None

    assert result.case_passed is True


async def test_test_fail_always_case():
    """持续测试失败后，Workflow 应在最大重试次数终止。"""

    case = next(case for case in EVALUATION_CASES if case.case_id == "test_fail_always")

    result = await run_evaluation_case(case)

    assert result.workflow_success is False
    assert result.tests_passed is False

    # Tester 一直失败，所以不会进入 Reviewer。
    assert result.review_verdict is None

    # supervisor.py 中 max_retry = 3。
    assert result.retry_count == 3

    assert result.failure_reason == ("max retry reached after test failure")

    assert result.case_passed is True

async def test_benchmark_summary():
    """验证 Dataset 能生成正确的整体 Benchmark 指标。"""

    dataset = await run_evaluation_dataset(EVALUATION_CASES)

    summary = dataset.summary

    assert summary.total_cases == 4

    # 4 个 Case 都表现出了预期行为。
    assert summary.benchmark_pass_rate == 1.0

    # login_success
    # review_reject_once
    # test_fail_once
    # 最终成功。
    #
    # test_fail_always 是预期失败。
    assert summary.workflow_success_rate == 0.75

    # 同理，最终测试通过的是前三个。
    assert summary.test_pass_rate == 0.75

    # 只有前三个进入 Reviewer，
    # 并且最终全部 APPROVE。
    assert summary.review_samples == 3
    assert summary.review_approval_rate == 1.0

    # review_reject_once
    # test_fail_once
    # test_fail_always
    # 都发生过 Retry。
    assert summary.retry_cases == 3

    # retry_count：
    # 0 + 1 + 1 + 3 = 5
    # 5 / 4 = 1.25
    assert summary.avg_retry_count == 1.25

    assert summary.max_retry_count == 3

    # 只有 test_fail_always 是预期失败场景，
    # 系统正确在 max retry 后停止。
    assert summary.expected_failure_cases == 1
    assert summary.expected_failure_pass_rate == 1.0
