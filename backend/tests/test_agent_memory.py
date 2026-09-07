"""测试 Coding Agent Memory 的保存、更新与召回。"""

import pytest
import pytest_asyncio
from sqlalchemy import select,delete

from app.agents.memory.service import (
    deactivate_memory,
    recall_memories,
    remember_successful_run,
    save_memory,
)
from app.db.base import AsyncSessionLocal, engine
from app.models.agent_memory import AgentMemory
from app.core.mock_client import MockLLM
from datetime import datetime, timedelta, timezone


@pytest_asyncio.fixture(autouse=True)
async def dispose_engine_after_test():
    """每个测试结束后释放 AsyncEngine 连接池，避免跨 Event Loop 复用连接。"""

    yield

    await engine.dispose()


@pytest.mark.asyncio
async def test_save_and_recall_memory():
    """验证 Memory 能写入 PostgreSQL，并在后续任务中重新召回。"""

    repository = "memory-test/example"

    # ---------------------------------------------------------
    # 1. 清理之前测试残留的数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. Remember：第一次保存 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="testing.command",
            summary="项目使用 pytest 运行测试",
            content="该仓库的主要测试命令为 pytest tests/。",
            importance=4,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 3. 再保存同一个 memory_key
    #    应该更新旧 Memory，而不是新增重复数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="testing.command",
            summary="项目测试命令已确认",
            content="该仓库使用 pytest tests/ 执行主要测试。",
            importance=5,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 4. Recall：模拟下一次任务读取历史 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            limit=5,
        )

        assert len(memories) == 1

        memory = memories[0]

        assert memory.embedding is not None
        assert len(memory.embedding) == 1536

        assert memory.memory_key == "testing.command"
        assert memory.memory_type == "SEMANTIC"
        assert memory.importance == 5
        assert memory.summary == "项目测试命令已确认"

        print()
        print("Recall Memory:")
        print(f"key: {memory.memory_key}")
        print(f"summary: {memory.summary}")
        print(f"content: {memory.content}")
        print(f"importance: {memory.importance}")

    # ---------------------------------------------------------
    # 5. 清理测试数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()


@pytest.mark.asyncio
async def test_remember_successful_run():
    """验证成功任务经过 Extractor 后形成长期 Memory，并能被 Recall。"""

    repository = "memory-test/successful-run"

    # ---------------------------------------------------------
    # 1. 清理之前测试残留
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. Remember
    #
    # 模拟一次成功 Coding Task：
    # Policy
    #   ↓
    # MockLLM Memory Extractor
    #   ↓
    # save_memory()
    #   ↓
    # PostgreSQL
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        saved_memories = await remember_successful_run(
            db,
            llm_client=MockLLM(),  # noqa: F821
            repository=repository,
            issue_number=42,
            issue_title="Fix login endpoint",
            issue_body=("Correct username and password cause the login endpoint to return 500."),
            solution_summary=(
                "Fixed incorrect access to user['name'] and changed it to user['username']."
            ),
            source_agent_run_id=None,
            success=True,
            test_result={
                "passed": True,
                "output": "5 passed",
            },
            review_result={
                "verdict": "APPROVE",
            },
            human_approved=True,
        )

        await db.commit()

        # MockLLM Extractor 固定返回 2 条 Memory。
        assert len(saved_memories) == 2

    # ---------------------------------------------------------
    # 3. Recall
    #
    # 模拟未来一次任务重新读取 Repository Memory。
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            limit=5,
        )

        assert len(memories) == 2

        memories_by_key = {memory.memory_key: memory for memory in memories}

        # -----------------------------------------------------
        # Semantic Memory
        # -----------------------------------------------------
        semantic_memory = memories_by_key["auth.user_field"]

        assert semantic_memory.memory_type == "SEMANTIC"
        assert semantic_memory.importance == 4
        assert "username" in semantic_memory.content

        # -----------------------------------------------------
        # Episodic Memory
        # -----------------------------------------------------
        episodic_memory = memories_by_key["auth.login_regression"]

        assert episodic_memory.memory_type == "EPISODIC"
        assert episodic_memory.importance == 3
        assert "pytest" in episodic_memory.content

        print()
        print("Recalled Extracted Memories:")

        for memory in memories:
            print(f"[{memory.memory_type}] {memory.memory_key}: {memory.summary}")

    # ---------------------------------------------------------
    # 4. 清理测试数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

@pytest.mark.asyncio
async def test_episodic_memories_keep_separate_history():
    """验证相同 key 的不同 Episodic Memory 不会互相覆盖。"""

    repository = "memory-test/episodic-history"

    # ---------------------------------------------------------
    # 1. 清理测试残留
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. 第一次历史经验
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await save_memory(
            db,
            repository=repository,
            memory_type="EPISODIC",
            memory_key="auth.related_tests",
            summary="第一次认证修改经验",
            content=("修改认证逻辑后需要运行 tests/test_auth.py。"),
            source_agent_run_id=None,
            importance=3,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 3. 第二次历史经验
    #
    # key 相同，但 Episodic 表示不同历史事件，
    # 所以不能把第一次覆盖掉。
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await save_memory(
            db,
            repository=repository,
            memory_type="EPISODIC",
            memory_key="auth.related_tests",
            summary="第二次认证修改经验",
            content=("修改认证依赖后除了 auth 测试，还需要运行 integration tests。"),
            source_agent_run_id=None,
            importance=4,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 4. Recall
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            limit=5,
        )

        # Episodic 是历史事件，两次经验都应该存在。
        assert len(memories) == 2

        summaries = {memory.summary for memory in memories}

        assert "第一次认证修改经验" in summaries
        assert "第二次认证修改经验" in summaries

        print()
        print("Episodic History:")

        for memory in memories:
            print(f"{memory.memory_key}: {memory.summary}")

    # ---------------------------------------------------------
    # 5. 清理测试数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()


@pytest.mark.asyncio
async def test_deactivated_memory_is_not_recalled():
    """验证失效 Memory 仍保存在数据库，但不会进入 Recall。"""

    repository = "memory-test/deactivate"

    # ---------------------------------------------------------
    # 1. 清理测试残留
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. 创建一条正常 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memory = await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="python.version",
            summary="项目使用 Python 3.10",
            content="该仓库当前运行在 Python 3.10。",
            importance=4,
        )

        await db.commit()

        memory_id = memory.id

    # ---------------------------------------------------------
    # 3. 让旧 Memory 失效
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        deactivated = await deactivate_memory(
            db,
            memory_id=memory_id,
        )

        await db.commit()

        assert deactivated is True

    # ---------------------------------------------------------
    # 4. Recall 不应该再返回它
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            limit=5,
        )

        assert memories == []

        # 但数据库里的记录仍然存在。
        result = await db.execute(select(AgentMemory).where(AgentMemory.id == memory_id))

        stored_memory = result.scalar_one()

        assert stored_memory.is_active is False
        assert stored_memory.memory_key == "python.version"

    # ---------------------------------------------------------
    # 5. 清理测试数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

@pytest.mark.asyncio
async def test_semantic_recall_returns_relevant_memory_first():
    """验证 Semantic Recall 会优先返回与当前 Issue 相关的 Memory。"""

    repository = "memory-test/semantic-recall"

    # ---------------------------------------------------------
    # 1. 清理测试数据
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. 保存三类完全不同的 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="auth.login_tests",
            summary=("Login authentication changes require login tests."),
            content=("When modifying login authentication, run pytest tests/test_login.py."),
            importance=3,
        )

        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="docker.deployment",
            summary="Docker deployment uses compose.",
            content=("Production deployment uses docker compose."),
            importance=5,
        )

        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="database.migrations",
            summary="Database migrations use Alembic.",
            content=("Schema changes require Alembic migrations."),
            importance=5,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 3. 当前 Issue 明显和 login/authentication 相关
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            query_text=("Fix login authentication bug. Login endpoint returns 500."),
            limit=3,
        )

        # Threshold 会过滤低相关 Memory，
        # 因此不要求一定返回 limit=3 条。
        assert len(memories) == 1

        assert memories[0].memory_key == "auth.login_tests"
        print()
        print("Semantic Recall Ranking:")

        for index, memory in enumerate(
            memories,
            start=1,
        ):
            print(f"{index}. {memory.memory_key}: {memory.summary}")

    # ---------------------------------------------------------
    # 4. 清理
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

@pytest.mark.asyncio
async def test_semantic_recall_filters_irrelevant_memories():
    """验证低相关 Memory 不会被强行 Recall。"""

    repository = "memory-test/semantic-threshold"

    # ---------------------------------------------------------
    # 1. 清理
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. 保存一些与登录问题无关的 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="docker.deployment",
            summary="Docker deployment uses compose.",
            content="Production deployment uses docker compose.",
            importance=5,
        )

        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="database.migrations",
            summary="Database migrations use Alembic.",
            content="Schema changes require Alembic migrations.",
            importance=5,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 3. 查询完全不同的话题
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            query_text=("Fix login authentication bug. Login endpoint returns 500."),
            limit=5,
        )

        # 两条 Memory 都与登录无关，
        # 即使 importance=5 也不能硬召回。
        assert memories == []

    # ---------------------------------------------------------
    # 4. 清理
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

@pytest.mark.asyncio
async def test_expired_memory_is_not_recalled():
    """验证过期 Memory 仍保存在数据库，但不会被 Recall。"""

    repository = "memory-test/expiration"

    # ---------------------------------------------------------
    # 1. 清理测试残留
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. 保存一条已经过期的 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        expired_memory = await save_memory(
            db,
            repository=repository,
            memory_type="EPISODIC",
            memory_key="auth.old_experience",
            summary="旧的认证修改经验",
            content="这是一条已经过期的历史经验。",
            importance=5,
            expires_at=(datetime.now(timezone.utc) - timedelta(days=1)),
        )

        expired_memory_id = expired_memory.id

        # 同时保存一条仍然有效的 Memory。
        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="auth.current_rule",
            summary="当前认证规则",
            content="认证模块当前使用 username 字段。",
            importance=3,
            expires_at=None,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 3. Recall
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            limit=5,
        )

        # 只应该召回未过期的 Memory。
        assert len(memories) == 1
        assert memories[0].memory_key == "auth.current_rule"

        # -----------------------------------------------------
        # 4. 过期 Memory 并没有被删除。
        # -----------------------------------------------------
        result = await db.execute(select(AgentMemory).where(AgentMemory.id == expired_memory_id))

        stored_memory = result.scalar_one()

        assert stored_memory.is_active is True
        assert stored_memory.expires_at is not None

    # ---------------------------------------------------------
    # 5. 清理
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

@pytest.mark.asyncio
async def test_expired_memory_is_not_recalled():
    """验证过期 Memory 仍保存在数据库，但不会被 Recall。"""

    repository = "memory-test/expiration"

    # ---------------------------------------------------------
    # 1. 清理测试残留
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()

    # ---------------------------------------------------------
    # 2. 保存一条已经过期的 Memory
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        expired_memory = await save_memory(
            db,
            repository=repository,
            memory_type="EPISODIC",
            memory_key="auth.old_experience",
            summary="旧的认证修改经验",
            content="这是一条已经过期的历史经验。",
            importance=5,
            expires_at=(datetime.now(timezone.utc) - timedelta(days=1)),
        )

        expired_memory_id = expired_memory.id

        # 同时保存一条仍然有效的 Memory。
        await save_memory(
            db,
            repository=repository,
            memory_type="SEMANTIC",
            memory_key="auth.current_rule",
            summary="当前认证规则",
            content="认证模块当前使用 username 字段。",
            importance=3,
            expires_at=None,
        )

        await db.commit()

    # ---------------------------------------------------------
    # 3. Recall
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        memories = await recall_memories(
            db,
            repository=repository,
            limit=5,
        )

        # 只应该召回未过期的 Memory。
        assert len(memories) == 1
        assert memories[0].memory_key == "auth.current_rule"

        # -----------------------------------------------------
        # 4. 过期 Memory 并没有被删除。
        # -----------------------------------------------------
        result = await db.execute(select(AgentMemory).where(AgentMemory.id == expired_memory_id))

        stored_memory = result.scalar_one()

        assert stored_memory.is_active is True
        assert stored_memory.expires_at is not None

    # ---------------------------------------------------------
    # 5. 清理
    # ---------------------------------------------------------
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMemory).where(AgentMemory.repository == repository))
        await db.commit()