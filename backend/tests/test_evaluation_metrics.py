"""测试 AgentRun 确定性 Evaluation Metrics。"""

from types import SimpleNamespace

from app.evaluation.metrics import (
    RunEvaluation,
    aggregate_evaluations,
    evaluate_agent_run,
)


def test_successful_agent_run_metrics():
    """验证成功 AgentRun 的 Evaluation 指标。"""

    agent_run = SimpleNamespace(
        status="COMPLETED",
        final_result={
            "success": True,
            "test_result": {
                "passed": True,
            },
            "review_result": {
                "verdict": "APPROVE",
            },
            "human_approved": True,
        },
        pr_number=42,
        pr_url=("https://github.com/example/repo/pull/42"),
        iteration=8,
        tokens_used=12000,
        tool_calls_made=15,
        elapsed_seconds=120,
        error=None,
    )

    evaluation = evaluate_agent_run(agent_run)

    assert evaluation.workflow_success is True
    assert evaluation.tests_passed is True
    assert evaluation.review_approved is True
    assert evaluation.human_approved is True
    assert evaluation.pr_created is True

    assert evaluation.quality_gate_passed is True

    assert evaluation.iterations == 8
    assert evaluation.tokens_used == 12000
    assert evaluation.tool_calls_made == 15
    assert evaluation.elapsed_seconds == 120

    assert evaluation.failure_reason is None


def test_failed_agent_run_metrics():
    """验证失败 AgentRun 不会通过 Quality Gate。"""

    agent_run = SimpleNamespace(
        status="FAILED",
        final_result={
            "success": False,
            "reason": "tests_failed",
            "test_result": {
                "passed": False,
            },
            "review_result": {},
        },
        pr_number=None,
        pr_url=None,
        iteration=5,
        tokens_used=6000,
        tool_calls_made=9,
        elapsed_seconds=60,
        error="tests_failed",
    )

    evaluation = evaluate_agent_run(agent_run)

    assert evaluation.workflow_success is False
    assert evaluation.tests_passed is False

    assert evaluation.review_approved is None
    assert evaluation.human_approved is None

    assert evaluation.pr_created is False
    assert evaluation.quality_gate_passed is False

    assert evaluation.failure_reason == "tests_failed"

def test_aggregate_evaluations():
    """验证多次 AgentRun 可以聚合成整体指标。"""

    evaluations = [
        RunEvaluation(
            workflow_success=True,
            tests_passed=True,
            review_approved=True,
            human_approved=True,
            pr_created=True,
            quality_gate_passed=True,
            iterations=8,
            tokens_used=10000,
            tool_calls_made=12,
            elapsed_seconds=100,
            status="COMPLETED",
        ),
        RunEvaluation(
            workflow_success=True,
            tests_passed=True,
            review_approved=True,
            human_approved=True,
            pr_created=True,
            quality_gate_passed=True,
            iterations=10,
            tokens_used=14000,
            tool_calls_made=16,
            elapsed_seconds=140,
            status="COMPLETED",
        ),
        RunEvaluation(
            workflow_success=False,
            tests_passed=False,
            review_approved=None,
            human_approved=None,
            pr_created=False,
            quality_gate_passed=False,
            iterations=6,
            tokens_used=8000,
            tool_calls_made=10,
            elapsed_seconds=60,
            status="FAILED",
            failure_reason="tests_failed",
        ),
    ]

    summary = aggregate_evaluations(evaluations)

    assert summary.total_runs == 3
    assert summary.failed_runs == 1

    assert summary.workflow_success_rate == 2 / 3
    assert summary.test_pass_rate == 2 / 3
    assert summary.review_approval_rate == 2 / 3
    assert summary.pr_creation_rate == 2 / 3
    assert summary.quality_gate_pass_rate == 2 / 3

    # 只有前两个 Run 有 HITL 数据。
    assert summary.human_approval_samples == 2
    assert summary.human_approval_rate == 1.0

    assert summary.avg_iterations == 8.0
    assert summary.avg_tokens_used == 10666.666666666666
    assert summary.avg_tool_calls == 12.666666666666666
    assert summary.avg_elapsed_seconds == 100.0