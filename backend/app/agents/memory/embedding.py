"""Coding Agent Memory Embedding 服务。"""

import asyncio
import hashlib
import math
import re

import litellm

from app.core.config import settings


def _tokenize(text: str) -> list[str]:
    """把英文单词和中文字符拆成简单 Token。"""

    return re.findall(
        r"[a-z0-9_]+|[\u4e00-\u9fff]",
        text.lower(),
    )


def _mock_embedding(
    text: str,
    *,
    dimensions: int,
) -> list[float]:
    """生成确定性的本地 Mock Embedding。

    不调用外部 API，并保留一定的词语重合相似度，
    方便 Semantic Recall 测试。
    """

    vector = [0.0] * dimensions

    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()

        index = (
            int.from_bytes(
                digest[:4],
                "big",
            )
            % dimensions
        )

        # 用哈希中的另一位决定正负方向。
        sign = 1.0 if digest[4] % 2 == 0 else -1.0

        vector[index] += sign

    # L2 Normalize，方便后面直接计算 cosine similarity。
    norm = math.sqrt(sum(value * value for value in vector))

    if norm == 0:
        return vector

    return [value / norm for value in vector]


async def embed_text(text: str) -> list[float]:
    """把文本转换成 Memory Embedding。"""

    dimensions = settings.MEMORY_EMBEDDING_DIMENSIONS

    # ---------------------------------------------------------
    # 开发 / 测试：本地 Mock
    # ---------------------------------------------------------
    if settings.MOCK_EMBEDDING:
        return _mock_embedding(
            text,
            dimensions=dimensions,
        )

    # ---------------------------------------------------------
    # 真实环境：LiteLLM Embedding
    # ---------------------------------------------------------
    response = await asyncio.to_thread(
        litellm.embedding,
        model=settings.MEMORY_EMBEDDING_MODEL,
        input=[text],
    )

    item = response.data[0]

    if isinstance(item, dict):
        embedding = item["embedding"]
    else:
        embedding = item.embedding

    embedding = list(embedding)

    if len(embedding) != dimensions:
        raise ValueError(
            f"Unexpected embedding dimensions: expected={dimensions}, actual={len(embedding)}"
        )

    return embedding
