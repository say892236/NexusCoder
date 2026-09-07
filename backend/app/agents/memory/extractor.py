"""从成功的 Coding Agent 执行结果中提炼长期 Memory。"""

import asyncio
import json
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import settings

from langsmith import traceable


class ExtractedMemory(BaseModel):
    """LLM 提炼出的一条候选长期记忆。"""

    memory_type: Literal["EPISODIC", "SEMANTIC"]

    memory_key: str = Field(
        min_length=1,
        max_length=500,
    )

    summary: str = Field(
        min_length=1,
        max_length=500,
    )

    content: str = Field(
        min_length=1,
    )

    importance: int = Field(
        ge=1,
        le=5,
    )


class MemoryExtractionResult(BaseModel):
    """一次任务最终提炼出的 Memory 列表。"""

    memories: list[ExtractedMemory] = Field(
        default_factory=list,
        max_length=3,
    )


MEMORY_EXTRACTOR_PROMPT = """You are a memory extraction component for a Coding Agent.

Your job is to examine a successfully completed coding task and extract
0 to 3 pieces of information that would genuinely help the agent solve
future tasks in the SAME repository.

## Memory Types

SEMANTIC:
Stable repository knowledge or conventions.

Examples:
- The repository uses pytest for tests.
- Authentication logic lives in app/services/auth.py.
- Database migrations are managed with Alembic.
- Protected branches must never be modified directly.

EPISODIC:
Reusable experience learned from a previous task.

Examples:
- Changing authentication validation required updating test_auth.py.
- A previous change failed because a specific integration test was missed.
- When modifying module X, module Y also needed updating.

## Rules

1. Only store information that could be useful in FUTURE tasks.
2. Do not simply summarize the current issue.
3. Do not store one-off implementation details with no reusable value.
4. Do not store secrets, tokens, credentials, or sensitive values.
5. Prefer fewer high-quality memories over many weak memories.
6. Memory keys should be stable dot-separated identifiers.

Good memory keys:
- testing.pytest_command
- auth.related_tests
- database.migration_tool
- api.error_handling

7. importance:
   1 = low value
   3 = useful
   5 = highly reusable

8. If there is nothing worth remembering, return an empty memories list.

Return ONLY valid JSON in this exact structure:

{
  "memories": [
    {
      "memory_type": "SEMANTIC",
      "memory_key": "testing.framework",
      "summary": "Repository uses pytest for automated tests.",
      "content": "Relevant changes should be validated with the repository's pytest test suite.",
      "importance": 4
    }
  ]
}
"""


def _clean_json_response(content: str) -> str:
    """清理模型偶尔返回的 Markdown JSON 代码块。"""

    content = content.strip()

    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    return content.strip()


def _trace_extractor_inputs(inputs: dict) -> dict:
    """只记录 Memory Extractor 的安全输入摘要。"""

    test_result = inputs.get("test_result") or {}

    review_result = inputs.get("review_result") or {}

    return {
        "repository": inputs.get("repository"),
        "issue_number": inputs.get("issue_number"),
        "issue_title": inputs.get("issue_title"),
        "test_passed": test_result.get("passed"),
        "review_verdict": review_result.get("verdict"),
    }


def _trace_extractor_outputs(memories) -> dict:
    """记录提炼结果摘要。"""

    return {
        "memory_count": len(memories),
        "memory_keys": [memory.memory_key for memory in memories],
        "memory_types": [memory.memory_type for memory in memories],
        "importance": [memory.importance for memory in memories],
    }

@traceable(
    name="memory_extractor",
    run_type="chain",
    process_inputs=_trace_extractor_inputs,
    process_outputs=_trace_extractor_outputs,
)
async def extract_memories_from_run(
    *,
    llm_client,
    repository: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    solution_summary: str,
    test_result: dict | None = None,
    review_result: dict | None = None,
) -> list[ExtractedMemory]:
    """从一次成功任务中提炼 0~3 条可复用 Memory。"""

    task_context = f"""## Repository

{repository}

## Completed Issue

#{issue_number} - {issue_title}

Description:
{issue_body}

## Solution

{solution_summary}

## Test Result

{json.dumps(test_result or {}, ensure_ascii=False)}

## Review Result

{json.dumps(review_result or {}, ensure_ascii=False)}
"""

    # 现有 LiteLLMClient 是同步接口。
    # 使用 to_thread，避免在 Celery 的 async 流程里阻塞 Event Loop。
    response = await asyncio.to_thread(
        llm_client.chat.completions.create,
        model=settings.MODEL_NAME,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": MEMORY_EXTRACTOR_PROMPT,
            },
            {
                "role": "user",
                "content": task_context,
            },
        ],
    )

    content = response.choices[0].message.content

    if not content:
        return []

    cleaned_content = _clean_json_response(content)

    try:
        payload = json.loads(cleaned_content)

        result = MemoryExtractionResult.model_validate(payload)

        return result.memories

    except (json.JSONDecodeError, ValueError):
        # Memory 属于增强能力。
        # 提炼失败不能让整个成功的 Coding Task 变成 FAILED。
        return []
