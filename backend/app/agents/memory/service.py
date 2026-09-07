"""Coding Agent Memory 的基础存储与读取服务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.memory.extractor import extract_memories_from_run
from app.agents.memory.policy import should_remember_run
from app.models.agent_memory import AgentMemory
from app.agents.memory.extractor import extract_memories_from_run
from app.agents.memory.policy import should_remember_run
from app.agents.memory.embedding import embed_text
from app.core.config import settings
from datetime import datetime, timezone,timedelta

from sqlalchemy import or_, select
from langsmith import traceable



def _utcnow() -> datetime:
    """返回 timezone-aware UTC 时间。"""

    return datetime.now(timezone.utc)



def get_memory_expiration(
    memory_type: str,
) -> datetime | None:
    """根据 Memory 类型生成默认过期时间。"""

    if memory_type == "EPISODIC":
        return _utcnow() + timedelta(days=90)

    return None


async def save_memory(
    db: AsyncSession,
    *,
    repository: str,
    memory_type: str,
    summary: str,
    content: str,
    memory_key: str | None = None,
    source_agent_run_id=None,
    importance: int = 1,
    metadata: dict | None = None,
    expires_at=None,
) -> AgentMemory:
    """保存一条 Memory。

    如果同一仓库、同一类型、同一 memory_key 已存在，
    则更新原 Memory，避免重复积累。
    """

    existing_memory = None

    if memory_key:
        conditions = [
            AgentMemory.repository == repository,
            AgentMemory.memory_type == memory_type,
            AgentMemory.memory_key == memory_key,
            AgentMemory.is_active == True,  # noqa: E712
        ]

        # ---------------------------------------------------------
        # Semantic Memory：
        # 同一个 repository + memory_key 表示同一个“当前事实”。
        # 新知识直接更新旧知识。
        # ---------------------------------------------------------
        if memory_type == "SEMANTIC":
            query = await db.execute(select(AgentMemory).where(*conditions))

            existing_memory = query.scalar_one_or_none()

    # ---------------------------------------------------------
    # Episodic Memory：
    # 每次 AgentRun 都是独立历史事件。
    #
    # 只有同一个 AgentRun 重复执行 Remember 时才更新，
    # 避免 Celery 重试等情况产生重复 Memory。
    # ---------------------------------------------------------
    elif memory_type == "EPISODIC" and source_agent_run_id is not None:
        query = await db.execute(
            select(AgentMemory).where(
                *conditions,
                AgentMemory.source_agent_run_id == source_agent_run_id,
            )
        )

        existing_memory = query.scalar_one_or_none()

    # 用 summary + content 表示这条 Memory 的语义。
    embedding_text = f"{summary}\n{content}"

    embedding = await embed_text(embedding_text)

    # 已存在：更新旧 Memory。
    if existing_memory:
        existing_memory.summary = summary
        existing_memory.content = content
        existing_memory.importance = importance
        existing_memory.memory_metadata = metadata or {}
        existing_memory.expires_at = expires_at

        # Memory 内容发生变化时，向量也必须重新生成。
        existing_memory.embedding = embedding

        if source_agent_run_id is not None:
            existing_memory.source_agent_run_id = source_agent_run_id

        await db.flush()

        return existing_memory

    # 不存在：创建新 Memory。
    memory = AgentMemory(
        repository=repository,
        memory_type=memory_type,
        memory_key=memory_key,
        summary=summary,
        content=content,
        embedding=embedding,
        source_agent_run_id=source_agent_run_id,
        importance=importance,
        memory_metadata=metadata or {},
        is_active=True,
        expires_at=expires_at,
    )

    db.add(memory)
    await db.flush()

    return memory


def _trace_recall_inputs(inputs: dict) -> dict:
    """只记录安全的 Memory Recall 输入摘要。"""

    query_text = str(inputs.get("query_text") or "")

    return {
        "repository": inputs.get("repository"),
        "limit": inputs.get("limit"),
        # 不上传完整 Issue 内容，只记录长度。
        "query_length": len(query_text),
    }


def _trace_recall_outputs(memories) -> dict:
    """只记录 Recall 结果摘要，不上传完整 Memory 内容。"""

    return {
        "memory_count": len(memories),
        "memory_keys": [memory.memory_key for memory in memories],
        "memory_types": [memory.memory_type for memory in memories],
    }


@traceable(
    name="memory_recall",
    run_type="retriever",
    process_inputs=_trace_recall_inputs,
    process_outputs=_trace_recall_outputs,
)
async def recall_memories(
    db: AsyncSession,
    *,
    repository: str,
    query_text: str | None = None,
    limit: int = 5,
) -> list[AgentMemory]:
    """召回当前 Repository 最相关的有效 Memory。

    有 query_text：
        使用 pgvector cosine distance 做语义检索。

    没有 query_text：
        退化为 importance + updated_at 排序。
    """

    # ---------------------------------------------------------
    # 1. 没有查询文本时，保留原来的基础 Recall。
    # ---------------------------------------------------------
    if not query_text or not query_text.strip():
        result = await db.execute(
            select(AgentMemory)
            .where(
                AgentMemory.repository == repository,
                AgentMemory.is_active == True,  # noqa: E712
                or_(
                    AgentMemory.expires_at.is_(None),
                    AgentMemory.expires_at > _utcnow(),
                ),
            )
            .order_by(
                AgentMemory.importance.desc(),
                AgentMemory.updated_at.desc(),
            )
            .limit(limit)
        )

        return list(result.scalars().all())

    # ---------------------------------------------------------
    # 2. 当前 Issue 生成 Query Embedding。
    # ---------------------------------------------------------
    query_embedding = await embed_text(query_text)

    # ---------------------------------------------------------
    # 3. Semantic Recall
    #
    # cosine distance 越小，语义越相似。
    # importance 作为第二排序条件。
    # ---------------------------------------------------------


# cosine distance 越小表示语义越相似。
    cosine_distance = AgentMemory.embedding.cosine_distance(query_embedding)

    result = await db.execute(
        select(AgentMemory)
        .where(
            AgentMemory.repository == repository,
            AgentMemory.is_active == True,  # noqa: E712
            AgentMemory.embedding.is_not(None),
            or_(
                AgentMemory.expires_at.is_(None),
                AgentMemory.expires_at > _utcnow(),
            ),
            # 低相关 Memory 不进入 Coder Prompt。
            cosine_distance <= settings.MEMORY_MAX_COSINE_DISTANCE,
        )
        .order_by(
            cosine_distance,
            AgentMemory.importance.desc(),
        )
        .limit(limit)
    )

    return list(result.scalars().all())


async def remember_successful_run(
    db: AsyncSession,
    *,
    llm_client,
    repository: str,
    issue_number: int,
    issue_title: str,
    issue_body: str,
    solution_summary: str,
    source_agent_run_id,
    success: bool = True,
    test_result: dict | None = None,
    review_result: dict | None = None,
    human_approved: bool | None = None,
) -> list[AgentMemory]:
    """从一次成功 Coding Task 中提炼并保存长期 Memory。"""

    # ---------------------------------------------------------
    # 1. Memory Policy
    # 先判断这次任务是否值得进入长期记忆。
    # ---------------------------------------------------------
    if not should_remember_run(
        success=success,
        test_result=test_result,
        review_result=review_result,
        human_approved=human_approved,
    ):
        return []


    trace_metadata = {
            "repository": repository,
            "issue_number": issue_number,
        }


    if source_agent_run_id is not None:
        trace_metadata["thread_id"] = str(source_agent_run_id)

    # ---------------------------------------------------------
    # 2. Memory Extractor
    # 让 LLM 从完整任务结果中提炼 0~3 条真正可复用的经验。
    # ---------------------------------------------------------
    extracted_memories = await extract_memories_from_run(
        llm_client=llm_client,
        repository=repository,
        issue_number=issue_number,
        issue_title=issue_title,
        issue_body=issue_body,
        solution_summary=solution_summary,
        test_result=test_result,
        review_result=review_result,
        langsmith_extra={
            "metadata": trace_metadata,
            "tags": [
                "memory",
                "extractor",
            ],
        },
    )

    saved_memories: list[AgentMemory] = []

    # ---------------------------------------------------------
    # 3. Save / Update
    # 同 repository + type + memory_key 会更新旧 Memory，
    # 因此这里天然包含基础去重与替换逻辑。
    # ---------------------------------------------------------
    for extracted in extracted_memories:
        memory = await save_memory(
            db,
            repository=repository,
            memory_type=extracted.memory_type,
            memory_key=extracted.memory_key,
            summary=extracted.summary,
            content=extracted.content,
            source_agent_run_id=source_agent_run_id,
            importance=extracted.importance,
            metadata={
                "issue_number": issue_number,
                "issue_title": issue_title,
            },
            expires_at=get_memory_expiration(extracted.memory_type),
        )

        saved_memories.append(memory)

    return saved_memories


async def deactivate_memory(
    db: AsyncSession,
    *,
    memory_id,
) -> bool:
    """让一条 Memory 失效，但保留历史记录。"""

    result = await db.execute(
        select(AgentMemory).where(
            AgentMemory.id == memory_id,
            AgentMemory.is_active == True,  # noqa: E712
        )
    )

    memory = result.scalar_one_or_none()

    if memory is None:
        return False

    memory.is_active = False

    await db.flush()

    return True


async def backfill_memory_embeddings(
    db: AsyncSession,
    *,
    batch_size: int = 100,
) -> int:
    """给历史 Memory 补齐缺失的 Embedding。"""

    result = await db.execute(
        select(AgentMemory)
        .where(
            AgentMemory.embedding.is_(None),
        )
        .limit(batch_size)
    )

    memories = list(result.scalars().all())

    for memory in memories:
        embedding_text = f"{memory.summary}\n{memory.content}"

        memory.embedding = await embed_text(embedding_text)

    await db.flush()

    return len(memories)
