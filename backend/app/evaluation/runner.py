"""Coding Agent Evaluation Dataset 执行器。"""

from pydantic import BaseModel, Field


from app.agents.multi_agent.graph import build_graph
from app.agents.sandbox.mock import MockSandbox
from app.core.client import get_llm_client
from app.core.mock_client import MockLLM
from app.evaluation.cases import (
    EvaluationCase,
    RealLLMEvaluationCase,
)

class UsageMetrics(BaseModel):
    """单个 Agent / Case 的累计 LLM 使用量。"""

    runs: int = 0

    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0


def _build_usage(
    usage: dict | None,
) -> UsageMetrics:
    """把 Graph State 中的 usage dict 转成统一指标对象。"""

    usage = usage or {}

    return UsageMetrics(
        runs=usage.get("runs", 0),
        tokens_used=usage.get("tokens_used", 0),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get(
            "completion_tokens",
            0,
        ),
        cache_hit_tokens=usage.get(
            "cache_hit_tokens",
            0,
        ),
        cache_miss_tokens=usage.get(
            "cache_miss_tokens",
            0,
        ),
    )


def _merge_usage(
    *usages: UsageMetrics,
) -> UsageMetrics:
    """合并多个 Agent 的 Usage。"""

    return UsageMetrics(
        runs=sum(
            usage.runs
            for usage in usages
        ),
        tokens_used=sum(
            usage.tokens_used
            for usage in usages
        ),
        prompt_tokens=sum(
            usage.prompt_tokens
            for usage in usages
        ),
        completion_tokens=sum(
            usage.completion_tokens
            for usage in usages
        ),
        cache_hit_tokens=sum(
            usage.cache_hit_tokens
            for usage in usages
        ),
        cache_miss_tokens=sum(
            usage.cache_miss_tokens
            for usage in usages
        ),
    )


class CaseEvaluation(BaseModel):
    """单个 Evaluation Case 的执行结果。"""

    case_id: str

    workflow_success: bool

    tests_passed: bool | None

    review_verdict: str | None

    workflow_match: bool

    tests_match: bool

    review_match: bool

    case_passed: bool

    retry_count: int

    retry_match: bool

    failure_reason: str | None

    failure_reason_match: bool

    # Coder 整个 Workflow 生命周期中的累计 Usage。
    coder_usage: UsageMetrics = Field(
        default_factory=UsageMetrics,
    )

    # Reviewer 整个 Workflow 生命周期中的累计 Usage。
    reviewer_usage: UsageMetrics = Field(
        default_factory=UsageMetrics,
    )

    # Coder + Reviewer 总 Usage。
    total_usage: UsageMetrics = Field(
        default_factory=UsageMetrics,
    )

class BenchmarkSummary(BaseModel):
    """Evaluation Dataset 的整体 Benchmark 指标。"""

    total_cases: int

    # Expected vs Actual：
    # Case 是否表现出了我们预期的行为。
    benchmark_pass_rate: float

    # 原始 Workflow 最终成功率。
    workflow_success_rate: float

    # 最终 Tester 通过率。
    test_pass_rate: float

    # Reviewer 实际执行样本。
    review_samples: int

    # 只在真正执行过 Reviewer 的样本中统计。
    review_approval_rate: float | None

    # Retry 行为。
    retry_cases: int
    avg_retry_count: float
    max_retry_count: int

    # 专门验证系统能否正确处理“预期失败”。
    expected_failure_cases: int
    expected_failure_pass_rate: float | None

        # =========================
    # LLM Usage
    # =========================

    llm_runs: int = 0

    coder_tokens: int = 0
    reviewer_tokens: int = 0

    total_tokens: int = 0
    avg_tokens_per_case: float = 0.0

    prompt_tokens: int = 0
    completion_tokens: int = 0

    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0

    cache_hit_rate: float | None = None


async def run_evaluation_case(
    case: EvaluationCase,
) -> CaseEvaluation:
    """运行一个 Evaluation Case 并验证结果。

    Mock Evaluation：
    - 使用 MockLLM；
    - scenario 控制固定测试行为；
    - 使用默认 login_500 MockSandbox。

    Real LLM Evaluation：
    - 使用真实 LLM Client；
    - 不通过 scenario 控制模型行为；
    - 根据 sandbox_fixture 创建对应评测仓库。
    """

    graph = build_graph()

    # ---------------------------------------------------------
    # 根据 Case 类型选择真实 LLM 或 Mock LLM。
    # ---------------------------------------------------------

    if isinstance(case, RealLLMEvaluationCase):
        sandbox = MockSandbox(
            fixture=case.sandbox_fixture,
        )

        llm_client = get_llm_client()

    else:
        sandbox = MockSandbox()

        llm_client = MockLLM(
            scenario=case.scenario,
        )

    try:
        result = await graph.ainvoke(
            {
                "repository": case.repository,
                "issue_number": case.issue_number,
                "issue_title": case.issue_title,
                "issue_body": case.issue_body,
                "custom_instructions": case.custom_instructions,
                "base_branch": case.base_branch,
                "retry_count": 0,
                "code_result": {},
                "test_result": {},
                "review_result": {},
            },
            context={
                "sandbox": sandbox,
                "llm_client": llm_client,
            },
            config={
                "recursion_limit": 50,
            },
        )

        final_result = (
            result.get("final_result")
            or {}
        )

        test_result = (
            result.get("test_result")
            or {}
        )

        review_result = (
            result.get("review_result")
            or {}
        )

        failure_reason = final_result.get(
            "reason"
        )

        workflow_success = (
            final_result.get("success")
            is True
        )

        tests_passed = test_result.get(
            "passed"
        )

        review_verdict = review_result.get(
            "verdict"
        )

        retry_count = result.get(
            "retry_count",
            0,
        )

        # -----------------------------------------------------
        # LLM Usage
        # -----------------------------------------------------

        coder_usage = _build_usage(
            result.get("coder_usage")
        )

        reviewer_usage = _build_usage(
            result.get("reviewer_usage")
        )

        total_usage = _merge_usage(
            coder_usage,
            reviewer_usage,
        )

        # -----------------------------------------------------
        # Expected vs Actual
        # -----------------------------------------------------

        workflow_match = (
            workflow_success
            == case.expected_success
        )

        tests_match = (
            tests_passed
            == case.expected_tests_passed
        )

        review_match = (
            review_verdict
            == case.expected_review_verdict
        )

        retry_match = (
            retry_count
            >= case.expected_min_retries
        )

        failure_reason_match = (
            failure_reason
            == case.expected_failure_reason
        )

        case_passed = (
            workflow_match
            and tests_match
            and review_match
            and retry_match
            and failure_reason_match
        )

        return CaseEvaluation(
            case_id=case.case_id,
            workflow_success=workflow_success,
            tests_passed=tests_passed,
            review_verdict=review_verdict,
            retry_count=retry_count,
            failure_reason=failure_reason,
            workflow_match=workflow_match,
            tests_match=tests_match,
            review_match=review_match,
            retry_match=retry_match,
            failure_reason_match=failure_reason_match,
            case_passed=case_passed,
            coder_usage=coder_usage,
            reviewer_usage=reviewer_usage,
            total_usage=total_usage,
        )

    finally:
        # Runner 创建 Sandbox，
        # 所以生命周期由 Runner 负责。
        sandbox.delete()

class DatasetEvaluation(BaseModel):
    """整个 Evaluation Dataset 的执行结果。"""

    total_cases: int

    passed_cases: int

    failed_cases: int

    pass_rate: float

    results: list[CaseEvaluation]

    summary: BenchmarkSummary

def build_benchmark_summary(
    cases: list[EvaluationCase],
    results: list[CaseEvaluation],
) -> BenchmarkSummary:
    """根据 Dataset 执行结果生成整体 Benchmark 指标。"""

    total_cases = len(results)

    if total_cases == 0:
        return BenchmarkSummary(
            total_cases=0,
            benchmark_pass_rate=0.0,
            workflow_success_rate=0.0,
            test_pass_rate=0.0,
            review_samples=0,
            review_approval_rate=None,
            retry_cases=0,
            avg_retry_count=0.0,
            max_retry_count=0,
            expected_failure_cases=0,
            expected_failure_pass_rate=None,
        )

    # ---------------------------------------------------------
    # Dataset Accuracy
    #
    # case_passed 不是“Workflow 成功”。
    # 它表示 Actual 是否符合这个 Case 的 Expected。
    # ---------------------------------------------------------

    passed_cases = sum(result.case_passed for result in results)

    benchmark_pass_rate = passed_cases / total_cases

    # ---------------------------------------------------------
    # Raw Workflow Metrics
    # ---------------------------------------------------------

    workflow_successes = sum(result.workflow_success for result in results)

    workflow_success_rate = workflow_successes / total_cases

    test_passed = sum(result.tests_passed is True for result in results)

    test_pass_rate = test_passed / total_cases

    # ---------------------------------------------------------
    # Reviewer
    #
    # test_fail_always 根本不会进入 Reviewer，
    # 所以不能把它算成 Reviewer Reject。
    # ---------------------------------------------------------

    reviewed_results = [result for result in results if result.review_verdict is not None]

    review_samples = len(reviewed_results)

    if review_samples:
        review_approvals = sum(result.review_verdict == "APPROVE" for result in reviewed_results)

        review_approval_rate = review_approvals / review_samples
    else:
        review_approval_rate = None

    # ---------------------------------------------------------
    # Retry
    # ---------------------------------------------------------

    retry_cases = sum(result.retry_count > 0 for result in results)

    avg_retry_count = sum(result.retry_count for result in results) / total_cases

    max_retry_count = max(result.retry_count for result in results)

    # ---------------------------------------------------------
    # LLM Usage Metrics
    # ---------------------------------------------------------

    llm_runs = sum(
        result.total_usage.runs
        for result in results
    )

    coder_tokens = sum(
        result.coder_usage.tokens_used
        for result in results
    )

    reviewer_tokens = sum(
        result.reviewer_usage.tokens_used
        for result in results
    )

    total_tokens = (
        coder_tokens
        + reviewer_tokens
    )

    avg_tokens_per_case = (
        total_tokens / total_cases
    )

    prompt_tokens = sum(
        result.total_usage.prompt_tokens
        for result in results
    )

    completion_tokens = sum(
        result.total_usage.completion_tokens
        for result in results
    )

    cache_hit_tokens = sum(
        result.total_usage.cache_hit_tokens
        for result in results
    )

    cache_miss_tokens = sum(
        result.total_usage.cache_miss_tokens
        for result in results
    )

    cache_hit_rate = (
        cache_hit_tokens / prompt_tokens
        if prompt_tokens
        else None
    )

    # ---------------------------------------------------------
    # Expected Failure
    #
    # 有些 Benchmark 本来就要求 Workflow 正确失败，
    # 比如 test_fail_always。
    # ---------------------------------------------------------

    expected_failure_pairs = [
        (case, result)
        for case, result in zip(
            cases,
            results,
            strict=True,
        )
        if case.expected_success is False
    ]

    expected_failure_cases = len(expected_failure_pairs)

    if expected_failure_cases:
        correctly_handled_failures = sum(result.case_passed for _, result in expected_failure_pairs)

        expected_failure_pass_rate = correctly_handled_failures / expected_failure_cases
    else:
        expected_failure_pass_rate = None

    return BenchmarkSummary(
        total_cases=total_cases,
        benchmark_pass_rate=benchmark_pass_rate,
        workflow_success_rate=workflow_success_rate,
        test_pass_rate=test_pass_rate,
        review_samples=review_samples,
        review_approval_rate=review_approval_rate,
        retry_cases=retry_cases,
        avg_retry_count=avg_retry_count,
        max_retry_count=max_retry_count,
        expected_failure_cases=expected_failure_cases,
        expected_failure_pass_rate=(expected_failure_pass_rate),
        llm_runs=llm_runs,

        coder_tokens=coder_tokens,
        reviewer_tokens=reviewer_tokens,

        total_tokens=total_tokens,
        avg_tokens_per_case=avg_tokens_per_case,

        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,

        cache_hit_tokens=cache_hit_tokens,
        cache_miss_tokens=cache_miss_tokens,

        cache_hit_rate=cache_hit_rate,
    )


async def run_evaluation_dataset(
    cases: list[EvaluationCase],
) -> DatasetEvaluation:
    """依次运行完整 Evaluation Dataset。"""

    results: list[CaseEvaluation] = []

    for case in cases:
        result = await run_evaluation_case(case)

        results.append(result)

    total_cases = len(results)

    passed_cases = sum(result.case_passed for result in results)

    failed_cases = total_cases - passed_cases

    pass_rate = passed_cases / total_cases if total_cases else 0.0

    summary = build_benchmark_summary(
        cases,
        results,
    )

    return DatasetEvaluation(
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        pass_rate=pass_rate,
        results=results,
        summary=summary
    )
