"""运行 Real LLM Coding Agent Evaluation Dataset。"""

import asyncio

from app.evaluation.cases import REAL_LLM_EVALUATION_CASES
from app.evaluation.runner import run_evaluation_dataset


def _format_rate(value: float | None) -> str:
    """把 0~1 的比例格式化成百分比。"""

    if value is None:
        return "N/A"

    return f"{value:.2%}"

def _cache_hit_rate(
    prompt_tokens: int,
    cache_hit_tokens: int,
) -> float | None:
    """计算 Prompt Cache 命中率。"""

    if prompt_tokens == 0:
        return None

    return (
        cache_hit_tokens
        / prompt_tokens
    )


async def main() -> None:
    """使用真实 LLM 运行 Evaluation Dataset 并打印报告。"""

    print("\nRunning Real LLM Coding Agent Evaluation...\n")

    dataset = await run_evaluation_dataset(
        REAL_LLM_EVALUATION_CASES,
    )

    # =========================================================
    # 每个 Real LLM Case 的执行结果
    # =========================================================

    print("\n========== Real LLM Evaluation Cases ==========\n")

    for result in dataset.results:
        status = "PASS" if result.case_passed else "FAIL"

        print(f"[{status}] {result.case_id}")
        print(
            f"  Workflow Success : "
            f"{result.workflow_success}"
        )
        print(
            f"  Tests Passed     : "
            f"{result.tests_passed}"
        )
        print(
            f"  Review Verdict   : "
            f"{result.review_verdict}"
        )
        print(
            f"  Retry Count      : "
            f"{result.retry_count}"
        )

        case_cache_hit_rate = _cache_hit_rate(
            result.total_usage.prompt_tokens,
            result.total_usage.cache_hit_tokens,
        )

        print(
            f"  Coder Tokens     : "
            f"{result.coder_usage.tokens_used}"
        )

        print(
            f"  Reviewer Tokens  : "
            f"{result.reviewer_usage.tokens_used}"
        )

        print(
            f"  Total Tokens     : "
            f"{result.total_usage.tokens_used}"
        )

        print(
            f"  Cache Hit Rate   : "
            f"{_format_rate(case_cache_hit_rate)}"
        )

        if result.failure_reason:
            print(
                f"  Failure Reason   : "
                f"{result.failure_reason}"
            )

        print()

    # =========================================================
    # Real LLM Benchmark Summary
    # =========================================================

    summary = dataset.summary

    print("========== Real LLM Benchmark Summary ==========\n")

    print(
        f"Total Cases             : "
        f"{summary.total_cases}"
    )

    print(
        f"Benchmark Pass Rate     : "
        f"{_format_rate(summary.benchmark_pass_rate)}"
    )

    print(
        f"Workflow Success Rate   : "
        f"{_format_rate(summary.workflow_success_rate)}"
    )

    print(
        f"Final Test Pass Rate    : "
        f"{_format_rate(summary.test_pass_rate)}"
    )

    print(
        f"Reviewer Approval Rate : "
        f"{_format_rate(summary.review_approval_rate)}"
    )

    print(
        f"Reviewer Samples        : "
        f"{summary.review_samples}"
    )

    print(
        f"Retry Cases             : "
        f"{summary.retry_cases}"
    )

    print(
        f"Average Retry Count     : "
        f"{summary.avg_retry_count:.2f}"
    )

    print(
        f"Max Retry Count         : "
        f"{summary.max_retry_count}"
    )

    print()

    print(
        f"LLM Runs                : "
        f"{summary.llm_runs}"
    )

    print(
        f"Coder Tokens            : "
        f"{summary.coder_tokens}"
    )

    print(
        f"Reviewer Tokens         : "
        f"{summary.reviewer_tokens}"
    )

    print(
        f"Total Tokens            : "
        f"{summary.total_tokens}"
    )

    print(
        f"Average Tokens / Case   : "
        f"{summary.avg_tokens_per_case:.2f}"
    )

    print(
        f"Prompt Tokens           : "
        f"{summary.prompt_tokens}"
    )

    print(
        f"Completion Tokens       : "
        f"{summary.completion_tokens}"
    )

    print(
        f"Cache Hit Tokens        : "
        f"{summary.cache_hit_tokens}"
    )

    print(
        f"Cache Miss Tokens       : "
        f"{summary.cache_miss_tokens}"
    )

    print(
        f"Cache Hit Rate          : "
        f"{_format_rate(summary.cache_hit_rate)}"
    )

    print("\n===============================================\n")


if __name__ == "__main__":
    asyncio.run(main())
