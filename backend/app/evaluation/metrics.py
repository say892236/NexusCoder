"""Coding Agent 单次执行的确定性 Evaluation Metrics。"""

from pydantic import BaseModel

from app.models.agent_run import AgentRun


class RunEvaluation(BaseModel):
    """一次 AgentRun 的核心质量与效率指标。"""

    # -------------------------
    # 质量指标
    # -------------------------

    workflow_success: bool

    tests_passed: bool | None

    review_approved: bool | None

    human_approved: bool | None

    pr_created: bool

    quality_gate_passed: bool

    # -------------------------
    # 效率指标
    # -------------------------

    iterations: int

    tokens_used: int

    tool_calls_made: int

    elapsed_seconds: int | None

    # -------------------------
    # 诊断信息
    # -------------------------

    status: str

    failure_reason: str | None = None

class EvaluationSummary(BaseModel):
    """多次 AgentRun 的聚合 Evaluation 指标。"""

    total_runs: int

    # -------------------------
    # 质量指标
    # -------------------------

    workflow_success_rate: float
    test_pass_rate: float
    review_approval_rate: float
    pr_creation_rate: float
    quality_gate_pass_rate: float

    # HITL 不是所有任务都一定存在，
    # 所以单独记录有效样本数。
    human_approval_rate: float | None
    human_approval_samples: int

    # -------------------------
    # 效率指标
    # -------------------------

    avg_iterations: float
    avg_tokens_used: float
    avg_tool_calls: float
    avg_elapsed_seconds: float | None

    # -------------------------
    # 失败统计
    # -------------------------

    failed_runs: int


def evaluate_agent_run(
    agent_run: AgentRun,
) -> RunEvaluation:
    """根据 AgentRun 持久化结果计算确定性指标。"""

    final_result = agent_run.final_result or {}

    test_result = final_result.get("test_result") or {}

    review_result = final_result.get("review_result") or {}

    # ---------------------------------------------------------
    # Workflow Success
    # ---------------------------------------------------------

    final_success = final_result.get("success")

    if final_success is None:
        # 兼容没有显式 success 字段的旧 AgentRun。
        workflow_success = agent_run.status == "COMPLETED"
    else:
        workflow_success = agent_run.status == "COMPLETED" and final_success is True

    # ---------------------------------------------------------
    # Test
    # ---------------------------------------------------------

    raw_test_passed = test_result.get("passed")

    tests_passed = raw_test_passed if isinstance(raw_test_passed, bool) else None

    # ---------------------------------------------------------
    # Reviewer
    # ---------------------------------------------------------

    verdict = review_result.get("verdict")

    if verdict is None:
        review_approved = None
    else:
        review_approved = verdict == "APPROVE"

    # ---------------------------------------------------------
    # HITL
    # ---------------------------------------------------------

    raw_human_approved = final_result.get("human_approved")

    human_approved = raw_human_approved if isinstance(raw_human_approved, bool) else None

    # ---------------------------------------------------------
    # PR
    # ---------------------------------------------------------

    pr_created = bool(agent_run.pr_number and agent_run.pr_url)

    # ---------------------------------------------------------
    # Overall Quality Gate
    #
    # 不做随意加权分数。
    # 只有所有关键质量条件真正满足才通过。
    # ---------------------------------------------------------

    quality_gate_passed = (
        workflow_success
        and tests_passed is True
        and review_approved is True
        and human_approved is not False
        and pr_created
    )

    failure_reason = final_result.get("reason") or agent_run.error

    return RunEvaluation(
        workflow_success=workflow_success,
        tests_passed=tests_passed,
        review_approved=review_approved,
        human_approved=human_approved,
        pr_created=pr_created,
        quality_gate_passed=quality_gate_passed,
        iterations=agent_run.iteration or 0,
        tokens_used=agent_run.tokens_used or 0,
        tool_calls_made=(agent_run.tool_calls_made or 0),
        elapsed_seconds=agent_run.elapsed_seconds,
        status=agent_run.status,
        failure_reason=failure_reason,
    )


def _rate(
    passed: int,
    total: int,
) -> float:
    """计算 0~1 之间的比例。"""

    if total == 0:
        return 0.0

    return passed / total


def aggregate_evaluations(
    evaluations: list[RunEvaluation],
) -> EvaluationSummary:
    """聚合多次 AgentRun 的 Evaluation 指标。"""

    total_runs = len(evaluations)

    if total_runs == 0:
        return EvaluationSummary(
            total_runs=0,
            workflow_success_rate=0.0,
            test_pass_rate=0.0,
            review_approval_rate=0.0,
            pr_creation_rate=0.0,
            quality_gate_pass_rate=0.0,
            human_approval_rate=None,
            human_approval_samples=0,
            avg_iterations=0.0,
            avg_tokens_used=0.0,
            avg_tool_calls=0.0,
            avg_elapsed_seconds=None,
            failed_runs=0,
        )

    # ---------------------------------------------------------
    # Quality
    # ---------------------------------------------------------

    workflow_successes = sum(evaluation.workflow_success for evaluation in evaluations)

    tests_passed = sum(evaluation.tests_passed is True for evaluation in evaluations)

    reviews_approved = sum(evaluation.review_approved is True for evaluation in evaluations)

    prs_created = sum(evaluation.pr_created for evaluation in evaluations)

    quality_gate_passed = sum(evaluation.quality_gate_passed for evaluation in evaluations)

    # ---------------------------------------------------------
    # HITL
    #
    # None 表示这个 Run 没有人工审批数据，
    # 不应该直接算成 Reject。
    # ---------------------------------------------------------

    human_results = [
        evaluation.human_approved
        for evaluation in evaluations
        if evaluation.human_approved is not None
    ]

    human_approval_samples = len(human_results)

    if human_results:
        human_approval_rate = _rate(
            sum(result is True for result in human_results),
            human_approval_samples,
        )
    else:
        human_approval_rate = None

    # ---------------------------------------------------------
    # Efficiency
    # ---------------------------------------------------------

    avg_iterations = sum(evaluation.iterations for evaluation in evaluations) / total_runs

    avg_tokens_used = sum(evaluation.tokens_used for evaluation in evaluations) / total_runs

    avg_tool_calls = sum(evaluation.tool_calls_made for evaluation in evaluations) / total_runs

    elapsed_values = [
        evaluation.elapsed_seconds
        for evaluation in evaluations
        if evaluation.elapsed_seconds is not None
    ]

    avg_elapsed_seconds = sum(elapsed_values) / len(elapsed_values) if elapsed_values else None

    failed_runs = sum(not evaluation.workflow_success for evaluation in evaluations)

    return EvaluationSummary(
        total_runs=total_runs,
        workflow_success_rate=_rate(
            workflow_successes,
            total_runs,
        ),
        test_pass_rate=_rate(
            tests_passed,
            total_runs,
        ),
        review_approval_rate=_rate(
            reviews_approved,
            total_runs,
        ),
        pr_creation_rate=_rate(
            prs_created,
            total_runs,
        ),
        quality_gate_pass_rate=_rate(
            quality_gate_passed,
            total_runs,
        ),
        human_approval_rate=human_approval_rate,
        human_approval_samples=(human_approval_samples),
        avg_iterations=avg_iterations,
        avg_tokens_used=avg_tokens_used,
        avg_tool_calls=avg_tool_calls,
        avg_elapsed_seconds=avg_elapsed_seconds,
        failed_runs=failed_runs,
    )