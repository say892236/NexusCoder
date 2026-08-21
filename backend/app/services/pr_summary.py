"""安全组合 PR 原描述与 Agent summary 的辅助函数。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SummaryComposeResult:
    """PR 描述与生成 summary 合并后的结果。"""

    body: str
    inserted_new_block: bool
    replaced_existing_block: bool


def compose_pr_description(
    existing_body: str | None,
    summary_markdown: str,
    mode: str = "append",
) -> SummaryComposeResult:
    """按 append 或 replace 模式生成最终 PR 描述。

    模式：
    - append：保留原正文，并追加 ``\\n --- \\n{summary}``。
    - replace：用 summary Markdown 替换整个描述。
    """
    normalized_mode = (mode or "append").strip().lower()
    if normalized_mode not in {"append", "replace"}:
        raise ValueError(f"Invalid summary mode '{mode}'. Use 'append' or 'replace'.")

    summary = summary_markdown.strip()
    current = (existing_body or "").strip()

    if normalized_mode == "replace":
        return SummaryComposeResult(
            body=summary,
            inserted_new_block=not bool(current),
            replaced_existing_block=bool(current),
        )

    if current:
        return SummaryComposeResult(
            body=f"{current.rstrip()}\n --- \n{summary}",
            inserted_new_block=True,
            replaced_existing_block=False,
        )

    return SummaryComposeResult(
        body=summary,
        inserted_new_block=True,
        replaced_existing_block=False,
    )
