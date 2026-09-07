"""基于 LiteLLM 的多 Provider LLM 客户端抽象。

通过 MODEL_NAME 可切换 Vertex AI、OpenAI、Anthropic、Mistral 等 Provider，同时向
AgentLoop 暴露与 OpenAI SDK 相同的 ``chat.completions.create()`` 接口，隔离模型差异。
"""

from typing import Any

import litellm

from app.core.config import settings
from app.core.mock_client import MockLLM

# 配置 LiteLLM 全局行为。
litellm.drop_params = True
litellm.set_verbose = False

# 启用 tracing 时注册 LangSmith callback。
if settings.LANGSMITH_TRACING:
    litellm.success_callback = ["langsmith"]
    litellm.failure_callback = ["langsmith"]


class _Completions:
    """模拟 ``openai.chat.completions`` 接口。"""

    def create(self, **kwargs: Any) -> Any:
        """通过 OpenAI 兼容接口调用 LiteLLM completion。

        Args:
            **kwargs: 传给 ``litellm.completion()`` 的参数，如 model、messages、tools

        Returns:
            OpenAI 兼容的 ModelResponse，包含 message、tool_calls 与 usage 等字段
        """
        return litellm.completion(**kwargs)


class _Chat:
    """模拟 ``openai.chat`` 接口。"""

    def __init__(self) -> None:
        """初始化 chat 接口。"""
        self.completions = _Completions()


class LiteLLMClient:
    """把调用委托给 LiteLLM 的 ``openai.OpenAI`` 兼容替代实现。

    保持 ``client.chat.completions.create()`` 接口不变，使 BaseAgent 与旧服务无需感知差异。
    """

    def __init__(self) -> None:
        """初始化 LiteLLM 客户端。"""
        self.chat = _Chat()


def get_llm_client():

    if settings.MOCK_LLM:

        print("🤖 使用 Mock LLM")

        return MockLLM()


    return LiteLLMClient()
