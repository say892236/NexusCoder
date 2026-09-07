"""后台 Coding Agent(Issue -> PR)的 system Prompt。"""

CODER_SYSTEM_PROMPT = """## Identity

You are NexusCoder, an autonomous senior software engineer operating inside a coding-agent workflow.

Your responsibility is to inspect the repository, implement the requested change, validate it, commit the result on a safe working branch, and explicitly complete the coding task.

The outer workflow is responsible for pull-request creation and human approval. Do not wait for human answers during your coding loop.

## Core Workflow

Follow this order:

1. Understand the issue and inspect relevant repository files.
2. Create or switch to a safe working branch.
3. Read files before modifying them.
4. Implement the smallest correct change that solves the issue.
5. Add or update tests when appropriate.
6. Run relevant tests when test infrastructure exists.
7. Fix failures caused by your changes.
8. Stage and commit meaningful changes.
9. Push the working branch when the configured remote is available.
10. Call `finish_task()` only after the coding work is ready.

## Repository Rules

- Never commit directly to protected branches such as:
  `main`, `master`, `prod`, `production`, `staging`,
  `stage`, `dev`, or `develop`.
- Stay focused on the requested issue.
- Follow the repository's existing architecture, naming, style, and dependencies.
- Prefer modifying existing code over introducing unnecessary abstractions.
- Do not change unrelated code unless it blocks the requested task.
- Use Conventional Commit messages when committing changes.

## Tool Usage

Use only the tools actually exposed to you through function calling.

General rules:

- Inspect before editing.
- Prefer dedicated file, Git, and test tools when available.
- Use `run_command` as a fallback when a specialized development tool fails.
- Do not repeatedly debug infrastructure failures such as authentication,
  network, permission, or unavailable external services.
- If infrastructure prevents a non-code operation, preserve the coding result
  and report the limitation through the final task summary.

Do not invent tools or arguments that are not present in the provided tool schemas.

## Coding Quality

- Match existing project conventions.
- Use clear names and appropriate types.
- Handle errors and validate external input when relevant.
- Never hardcode secrets.
- Never log sensitive values.
- Avoid unnecessary dependencies.
- Keep changes minimal and maintainable.
- Add tests for new behavior when the repository already has test infrastructure.

## Testing Rules

When tests exist:

- Run the relevant tests before completion.
- Treat failing relevant tests as blocking.
- Diagnose the failure using the actual test output.
- Modify the implementation and rerun tests until the relevant tests pass,
  unless the failure is clearly caused by unrelated infrastructure.

When no test infrastructure exists:

- Use reasonable targeted validation instead.

Do not call `finish_task()` while known required tests are failing.

## Retry Feedback

The outer workflow may invoke you again after a Tester or Reviewer rejects the previous result.

When a `Retry Context` is provided:

1. Treat it as feedback from the previous workflow attempt.
2. Inspect the current repository state before making another change.
3. Use test failures or review feedback to determine what remains incorrect.
4. Do not blindly repeat the previous solution.
5. Preserve valid existing work and change only what is necessary.

## Repository Memory

Historical repository memories may be provided with the task.

Use them as hints, not as authoritative facts:

- Verify important memories against the current repository.
- Prefer current code, tests, and issue requirements when they conflict.
- Do not blindly reproduce an old solution.

## Completion Contract

Call `finish_task(summary, branch_name)` exactly once when the coding task is ready.

Before completion, verify that:

- the requested issue has been addressed;
- relevant tests pass when tests exist;
- changes are committed on a safe working branch;
- there are no known required test failures.

The summary should briefly explain what changed and how it was validated.
"""


def build_coder_prompt(
    repository: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    custom_instructions: str = "",
    recalled_memories: list[dict[str, object]] | None = None,
    retry_count: int = 0,
    test_result: dict | None = None,
    review_result: dict | None = None,
) -> tuple[str, str]:
    """用动态 Issue 上下文构造 Coding Agent Prompt。

    Args:
        repository: Repository 名称（owner/repo）
        issue_number: GitHub Issue 编号
        issue_title: Issue 标题
        issue_body: Issue 描述
        custom_instructions: 用户补充指令

    Returns:
        ``(system_prompt, initial_user_message)`` 元组
    """
    memory_lines = []

    for memory in recalled_memories or []:
        memory_type = str(memory.get("memory_type", "MEMORY"))

        summary = str(memory.get("summary", "")).strip()

        content = str(memory.get("content", "")).strip()

        if not summary and not content:
            continue

        memory_text = f"- [{memory_type}] {summary}"

        if content and content != summary:
            memory_text += f"\n  Details: {content}"

        memory_lines.append(memory_text)

    memory_context = "\n".join(memory_lines) if memory_lines else "No relevant historical memories."

    system_prompt = CODER_SYSTEM_PROMPT


    # =========================================================
    # Retry Feedback
    # =========================================================

    retry_feedback = ""

    if retry_count > 0:
        feedback_lines = [
            "## Retry Context",
            "",
            (
                f"This is retry attempt #{retry_count}. "
                "The previous implementation did not fully pass "
                "the workflow quality checks."
            ),
        ]

        # -------------------------
        # Tester Feedback
        # -------------------------

        if test_result:
            test_passed = test_result.get("passed")

            if test_passed is False:
                feedback_lines.extend(
                    [
                        "",
                        "### Previous Test Failure",
                        ("The previous implementation failed the automated test stage."),
                    ]
                )

                test_output = str(test_result.get("output") or "").strip()

                if test_output:
                    # 避免超长 pytest 输出占用过多上下文。
                    test_output = test_output[-4000:]

                    feedback_lines.extend(
                        [
                            "",
                            "```text",
                            test_output,
                            "```",
                        ]
                    )

        # -------------------------
        # Reviewer Feedback
        # -------------------------

        if review_result:
            verdict = str(review_result.get("verdict") or "").upper()

            if verdict and verdict != "APPROVE":
                feedback_lines.extend(
                    [
                        "",
                        "### Previous Review Feedback",
                        f"Verdict: {verdict}",
                    ]
                )

                summary = str(review_result.get("summary") or "").strip()

                if summary:
                    feedback_lines.append(f"Reviewer summary: {summary}")

                severity = str(review_result.get("overall_severity") or "").strip()

                if severity:
                    feedback_lines.append(f"Severity: {severity}")

        feedback_lines.extend(
            [
                "",
                (
                    "Inspect the current repository state and "
                    "address the failure feedback before completing "
                    "the task again."
                ),
            ]
        )

        retry_feedback = "\n".join(feedback_lines)


    # =========================================================
    # Current Task Context
    # =========================================================

    base_user_context = f"""# Repository Context

    Repository: {repository}

    # GitHub Issue #{issue_number}

    **Title**: {issue_title}

    **Description**:
    {issue_body}

    ## Custom Instructions

    {custom_instructions or "No additional instructions."}

    ## Relevant Repository Memories

    {memory_context}

    ## Task

    Solve the issue using the repository and tools available to you.

    Inspect the current codebase, implement the necessary changes, validate the result, commit the work on a safe branch, and call `finish_task()` when the coding task is ready.
    """.strip()


    # Retry Feedback 只追加到原始 Prompt 末尾，
    # 尽可能保持前缀稳定，利于上下文缓存。
    if retry_feedback:
        user_context = f"{base_user_context}\n\n{retry_feedback}"
    else:
        user_context = base_user_context

    return system_prompt, user_context
