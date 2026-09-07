"""测试 Coding Agent Memory Extractor。"""

import pytest

from app.agents.memory.extractor import extract_memories_from_run
from app.core.mock_client import MockLLM


@pytest.mark.asyncio
async def test_extract_memories_from_successful_run():
    """验证 LLM 能从一次成功任务中提炼结构化 Memory。"""

    llm_client = MockLLM()

    memories = await extract_memories_from_run(
        llm_client=llm_client,
        repository="mock/repository",
        issue_number=42,
        issue_title="Fix login endpoint",
        issue_body=("Correct username and password cause the login endpoint to return 500."),
        solution_summary=(
            "Fixed incorrect access to user['name'] and changed it to user['username']."
        ),
        test_result={
            "passed": True,
            "output": "5 passed",
        },
        review_result={
            "verdict": "APPROVE",
        },
    )

    assert len(memories) == 2

    semantic_memory = memories[0]

    assert semantic_memory.memory_type == "SEMANTIC"
    assert semantic_memory.memory_key == "auth.user_field"
    assert semantic_memory.importance == 4
    assert "username" in semantic_memory.content

    episodic_memory = memories[1]

    assert episodic_memory.memory_type == "EPISODIC"
    assert episodic_memory.memory_key == "auth.login_regression"
    assert episodic_memory.importance == 3

    print()
    print("Extracted Memories:")

    for memory in memories:
        print(f"[{memory.memory_type}] {memory.memory_key}: {memory.summary}")
