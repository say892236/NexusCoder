"""运行 Coding Agent Evaluation Dataset 并输出 Benchmark Report。"""

import asyncio

from app.evaluation.cases import EVALUATION_CASES
from app.evaluation.runner import run_evaluation_dataset


def _format_rate(value: float | None) -> str:
    """把 0~1 的比例格式化成百分比。"""

    if value is None:
        return "N/A"

    return f"{value:.2%}"


async def main() -> None:
    """运行完整 Evaluation Dataset 并打印报告。"""

    print("\nRunning Coding Agent Evaluation...\n")

    dataset = await run_evaluation_dataset(EVALUATION_CASES)

    # =========================================================
    # 每个 Case 的执行结果
    # =========================================================

    print("========== Evaluation Cases ==========\n")

    for result in dataset.results:
        status = "PASS" if result.case_passed else "FAIL"

        print(f"[{status}] {result.case_id}")
        print(f"  Workflow Success : {result.workflow_success}")
        print(f"  Tests Passed     : {result.tests_passed}")
        print(f"  Review Verdict   : {result.review_verdict}")
        print(f"  Retry Count      : {result.retry_count}")

        if result.failure_reason:
            print(f"  Failure Reason   : {result.failure_reason}")

        print()

    # =========================================================
    # 整体 Benchmark
    # =========================================================

    summary = dataset.summary

    print("========== Benchmark Summary ==========\n")

    print(f"Total Cases                : {summary.total_cases}")

    print(f"Benchmark Pass Rate        : {_format_rate(summary.benchmark_pass_rate)}")

    print(f"Workflow Success Rate      : {_format_rate(summary.workflow_success_rate)}")

    print(f"Final Test Pass Rate       : {_format_rate(summary.test_pass_rate)}")

    print(f"Reviewer Approval Rate     : {_format_rate(summary.review_approval_rate)}")

    print(f"Reviewer Samples           : {summary.review_samples}")

    print(f"Retry Cases                : {summary.retry_cases}")

    print(f"Average Retry Count        : {summary.avg_retry_count:.2f}")

    print(f"Max Retry Count            : {summary.max_retry_count}")

    print(f"Expected Failure Cases     : {summary.expected_failure_cases}")

    print(f"Failure Handling Rate      : {_format_rate(summary.expected_failure_pass_rate)}")

    print("\n=======================================\n")


if __name__ == "__main__":
    asyncio.run(main())
