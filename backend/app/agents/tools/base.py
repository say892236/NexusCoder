"""Agent Tool 的定义、执行结果与抽象基类。"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """符合 OpenAI function calling 格式的 Tool 定义。"""

    name: str
    description: str
    parameters: dict[str, Any]


class ToolResult(BaseModel):
    """Tool 执行结果；同时承载成功数据、错误与诊断元数据。"""

    success: bool
    data: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """所有基于 Daytona Sandbox 的 Tool 抽象基类。"""

    def __init__(self, sandbox):
        """使用 Daytona Sandbox 初始化 Tool。

        Args:
            sandbox: Daytona Sandbox 实例
        """
        self.sandbox = sandbox

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回供 LLM Tool Calling 使用的定义。"""

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """通过 Daytona SDK 执行 Tool，由子类实现。

        Args:
            **kwargs: 当前 Tool 的结构化参数

        Returns:
            包含 success、data、error 的 ToolResult
        """

    def to_openai_schema(self) -> dict[str, Any]:
        """转换为 OpenAI function calling schema。

        Returns:
            OpenAI function calling 格式字典
        """
        return {
            "type": "function",
            "function": {
                "name": self.definition.name,
                "description": self.definition.description,
                "parameters": self.definition.parameters,
            },
        }
