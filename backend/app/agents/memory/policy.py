"""Coding Agent Memory 写入策略。"""


def should_remember_run(
    *,
    success: bool,
    test_result: dict | None = None,
    review_result: dict | None = None,
    human_approved: bool | None = None,
) -> bool:
    """判断一次 Coding 任务是否值得写入长期 Memory。

    第一版采用高精度策略：
    只有真正成功、测试通过、评审通过，并且没有被人工拒绝的任务才写入。
    """

    if not success:
        return False

    test_result = test_result or {}
    review_result = review_result or {}

    # 有测试结果时，必须通过。
    if "passed" in test_result and test_result.get("passed") is not True:
        return False

    # 有 Reviewer 结果时，必须 APPROVE。
    verdict = review_result.get("verdict")

    if verdict and verdict != "APPROVE":
        return False

    # HITL 明确拒绝时不能记。
    return human_approved is not False
