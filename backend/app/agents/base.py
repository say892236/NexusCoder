"""所有 Agent 共用的状态模型与单轮执行骨架。

``BaseAgent.run()`` 展示了核心 Tool Calling：把消息与 Tool schema 交给 LLM，解析
返回的 tool_calls，通过 ToolManager 执行，再将 ToolResult 以 ``role=tool`` 写回消息历史，
供下一轮 LLM 继续推理。完成类 Tool 会显式终止循环并产出结构化结果。
"""

import json
import logging
import time
from abc import ABC
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.utils.agent_logger import setup_agent_logger

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    """Agent 在内存执行过程中的状态。"""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentState(BaseModel):
    """记录迭代、资源消耗、消息历史与最终结果的 Agent 状态。"""

    agent_id: str
    status: AgentStatus = AgentStatus.PENDING

    iteration: int = 0

    # 所有请求处理的总 Token：
    # prompt_tokens + completion_tokens。
    tokens_used: int = 0

    # 输入 Token 总量。
    prompt_tokens: int = 0

    # 模型输出 Token 总量。
    completion_tokens: int = 0

    # DeepSeek Context Cache 命中输入 Token。
    cache_hit_tokens: int = 0

    # 未命中缓存的输入 Token。
    cache_miss_tokens: int = 0

    tool_calls_made: int = 0

    start_time: float = Field(default_factory=time.time)
    last_update: float = Field(default_factory=time.time)

    context: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    error: str | None = None

    messages: list[dict[str, Any]] = Field(default_factory=list)


class BaseAgent(ABC):
    """封装 LLM 调用、Tool Calling 和停止条件的 Agent 基类。"""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        initial_user_message: str,
        tools,
        llm_client,
        max_iterations: int = 20,
        max_tokens: int = 100_000,
        max_tool_calls: int = 30,
        max_duration_seconds: int = 180,
    ):
        """初始化 Agent 的 Prompt、Tool、LLM 客户端与资源预算。

        Args:
            agent_id: Agent 的唯一 ID
            system_prompt: 约束 Agent 行为的 system Prompt
            initial_user_message: 携带任务上下文的首条用户消息
            tools: ToolManager 实例
            llm_client: 发起 LLM 调用的 OpenAI 客户端
            max_iterations: 最大迭代轮数
            max_tokens: 最大 token 用量
            max_tool_calls: 最大 Tool 调用次数
            max_duration_seconds: 最大执行时长（秒）
        """
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.initial_user_message = initial_user_message
        self.tools = tools
        self.llm = llm_client
        self.max_iterations = max_iterations
        self.max_tokens = max_tokens
        self.max_tool_calls = max_tool_calls
        self.max_duration_seconds = max_duration_seconds

        # 初始化状态，并用 system/user 两条消息建立首次 LLM 调用上下文。
        self.state = AgentState(agent_id=agent_id)
        self.state.messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": initial_user_message},
        ]

        # 每个 Agent 单独记录文件日志，便于按 agent_id 复盘。
        self.agent_logger = setup_agent_logger(agent_id)

    async def run(self) -> bool:
        """执行一轮 LLM -> Tool -> Message History。

        Returns:
            未完成时返回 True；完成 Tool 发出终止信号时返回 False。
        """
        self.state.iteration += 1
        self.state.last_update = time.time()
        self.state.status = AgentStatus.EXECUTING

        self.agent_logger.debug(f"Agent {self.agent_id} - Iteration {self.state.iteration}")

        try:
            # 将历史消息和全部 Tool schema 发给 LLM，由模型选择是否调用 Tool。
            response = self.llm.chat.completions.create(
                model=settings.MODEL_NAME,
                messages=self.state.messages,
                tools=self.tools.get_all_schemas(),
                temperature=1.0,
            )

            message = response.choices[0].message

            # 以响应 usage 为准累计真实 token 消耗，而不是本地估算。
            if hasattr(response, "usage") and response.usage:
                usage = response.usage

                prompt_tokens = int(
                    getattr(usage, "prompt_tokens", 0)
                    or 0
                )

                completion_tokens = int(
                    getattr(usage, "completion_tokens", 0)
                    or 0
                )

                total_tokens = int(
                    getattr(usage, "total_tokens", 0)
                    or 0
                )

                # =====================================================
                # Context Cache
                # =====================================================

                # DeepSeek 原生 usage 可能直接提供：
                # prompt_cache_hit_tokens /
                # prompt_cache_miss_tokens。
                cache_hit_tokens = int(
                    getattr(
                        usage,
                        "prompt_cache_hit_tokens",
                        0,
                    )
                    or 0
                )

                cache_miss_tokens = int(
                    getattr(
                        usage,
                        "prompt_cache_miss_tokens",
                        0,
                    )
                    or 0
                )

                # LiteLLM 还会把缓存命中统一映射到
                # prompt_tokens_details.cached_tokens。
                prompt_details = getattr(
                    usage,
                    "prompt_tokens_details",
                    None,
                )

                if (
                    cache_hit_tokens == 0
                    and prompt_details is not None
                ):
                    if isinstance(prompt_details, dict):
                        cache_hit_tokens = int(
                            prompt_details.get(
                                "cached_tokens",
                                0,
                            )
                            or 0
                        )
                    else:
                        cache_hit_tokens = int(
                            getattr(
                                prompt_details,
                                "cached_tokens",
                                0,
                            )
                            or 0
                        )

                # 如果 LiteLLM 没保留 DeepSeek 的 miss 字段，
                # 可根据 prompt 总量计算。
                if cache_miss_tokens == 0:
                    cache_miss_tokens = max(
                        prompt_tokens - cache_hit_tokens,
                        0,
                    )

                # =====================================================
                # 累计 Agent Token Metrics
                # =====================================================

                self.state.tokens_used += total_tokens

                self.state.prompt_tokens += prompt_tokens

                self.state.completion_tokens += (
                    completion_tokens
                )

                self.state.cache_hit_tokens += (
                    cache_hit_tokens
                )

                self.state.cache_miss_tokens += (
                    cache_miss_tokens
                )

                self.agent_logger.debug(
                    "Token usage: "
                    f"prompt={prompt_tokens}, "
                    f"cache_hit={cache_hit_tokens}, "
                    f"cache_miss={cache_miss_tokens}, "
                    f"completion={completion_tokens}, "
                    f"total={total_tokens}, "
                    f"agent_total={self.state.tokens_used}"
                )

            # 同时提取自然语言内容和结构化 tool_calls。
            content = message.content or ""
            tool_calls_data = self._extract_tool_calls(response)

            # 文本内容只用于诊断；真正的环境操作由 Tool 执行。
            if content:
                self.agent_logger.debug(f"Agent Response Content: {content[:200]}")

            # 一次响应可包含多个 Tool call，ToolManager 会并发执行它们。
            if tool_calls_data:
                self.agent_logger.debug(
                    f"Agent made {len(tool_calls_data)} Tool Calls: {[tc['name'] for tc in tool_calls_data]}"
                )
                results = await self.tools.execute_batch(tool_calls_data)
                self.state.tool_calls_made += len(tool_calls_data)
                self._log_tool_execution_details(tool_calls_data, results)

                # finish_review/finish_task 等完成 Tool 会携带 completed 信号。
                if self._is_complete(results):
                    self.state.status = AgentStatus.COMPLETED
                    self.state.result = self._extract_final_result(results)
                    self.agent_logger.debug(f"Agent {self.agent_id} completed task")
                    return False  # 完成 Tool 已返回结构化结果，停止当前 Agent。

                # 把每个 ToolResult 写回消息历史，下一轮 LLM 才能看到执行结果。
                self._add_tool_results_to_messages(tool_calls_data, results)

            else:
                # 没有 Tool call 时保留 assistant 文本，让对话仍能继续。
                self.agent_logger.debug(f"Agent {self.agent_id} made no tool calls")
                # 追加 assistant 消息后进入下一轮。
                if content:
                    self.state.messages.append({"role": "assistant", "content": content})

            return True

        except Exception as e:
            logger.error(f"Agent {self.agent_id} iteration failed: {e}", exc_info=True)
            self.state.status = AgentStatus.FAILED
            self.state.error = str(e)
            return False

    def should_stop(self) -> bool:
        """
        根据完成状态与资源预算判断是否停止 Agent。

        Returns:
            需要停止时返回 True，否则返回 False。
        """

        # 已完成或失败的 Agent 不再进入下一轮。
        if self.state.status in (
            AgentStatus.COMPLETED,
            AgentStatus.FAILED,
        ):
            return True

        # 迭代轮数上限。
        if self.state.iteration >= self.max_iterations:
            reason = "max_iterations_reached"

            logger.warning(f"Agent {self.agent_id} reached max iterations: {self.state.iteration}")

            self.state.status = AgentStatus.FAILED
            self.state.error = reason
            self.state.result = {
                "completed": False,
                "reason": reason,
            }

            return True

        # Token 预算上限。
        if self.state.tokens_used >= self.max_tokens:
            reason = "max_tokens_reached"

            logger.warning(f"Agent {self.agent_id} reached max tokens: {self.state.tokens_used}")

            self.state.status = AgentStatus.FAILED
            self.state.error = reason
            self.state.result = {
                "completed": False,
                "reason": reason,
            }

            return True

        # Tool 调用次数上限。
        if self.state.tool_calls_made >= self.max_tool_calls:
            reason = "max_tool_calls_reached"

            logger.warning(
                f"Agent {self.agent_id} reached max tool calls: {self.state.tool_calls_made}"
            )

            self.state.status = AgentStatus.FAILED
            self.state.error = reason
            self.state.result = {
                "completed": False,
                "reason": reason,
            }

            return True

        # 总执行时长上限。
        elapsed = time.time() - self.state.start_time

        if elapsed >= self.max_duration_seconds:
            reason = "max_duration_reached"

            logger.warning(f"Agent {self.agent_id} reached max duration: {elapsed:.2f}s")

            self.state.status = AgentStatus.FAILED
            self.state.error = reason
            self.state.result = {
                "completed": False,
                "reason": reason,
            }

            return True

        return False

    def _extract_tool_calls(self, llm_response) -> list[dict[str, Any]]:
        """把 LLM 响应中的 tool_calls 规范化为 ToolManager 所需结构。"""
        message = llm_response.choices[0].message
        if not message.tool_calls:
            return []

        tool_calls = []
        for tc in message.tool_calls:
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments),
                }
            )
        return tool_calls

    def _is_complete(self, tool_results: dict) -> bool:
        """检查是否有 ToolResult 发出任务完成信号。

        Args:
            tool_results: Tool call ID 到 ToolResult 的映射

        Returns:
            调用了完成 Tool 时返回 True
        """
        for result in tool_results.values():
            if result.success and result.data:
        # 只要 ToolResult.data.completed=True，就视为完成。
                if isinstance(result.data, dict) and result.data.get("completed"):
                    return True
        return False

    def _extract_final_result(self, tool_results: dict) -> dict[str, Any]:
        """从完成 Tool 中提取要持久化的最终结构化结果。

        Args:j
            tool_results: Tool call ID 到 ToolResult 的映射

        Returns:
            最终结果数据
        """
        for result in tool_results.values():
            if result.success and result.data:
                if isinstance(result.data, dict) and result.data.get("completed"):
                    return result.data
        return {}

    def _add_tool_results_to_messages(self, tool_calls: list, results: dict) -> None:
        """按 OpenAI Tool Calling 协议把调用及结果加入消息历史。

        Args:
            tool_calls: Tool call 字典列表
            results: Tool call ID 到 ToolResult 的映射
        """
        # 先写入带 tool_calls 的 assistant 消息，建立调用关系。
        self.state.messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )

        # 再为每个 call_id 写入对应的 role=tool 结果消息。
        for tc in tool_calls:
            result = results.get(tc["id"])
            content = json.dumps(result.model_dump() if result else {"error": "No result"})

            self.state.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": content,
                }
            )

    def _log_tool_execution_details(self, tool_calls: list, results: dict) -> None:
        """记录每个 Tool 的参数、结果与元数据，便于定位执行问题。"""
        for tc in tool_calls:
            result = results.get(tc["id"])
            if not result:
                self.agent_logger.error(
                    f"Tool result missing for call_id={tc['id']} tool={tc['name']}"
                )
                continue

            metadata = result.metadata or {}
            tool_args = metadata.get("tool_args", tc.get("arguments", {}))
            status = "SUCCESS" if result.success else "FAILED"

            if result.success:
                self.agent_logger.debug(
                    f"Tool {status}: {tc['name']} args={json.dumps(tool_args, default=str)[:1200]} "
                    f"metadata={json.dumps(metadata, default=str)[:1200]}"
                )
            else:
                self.agent_logger.error(
                    f"Tool {status}: {tc['name']} args={json.dumps(tool_args, default=str)[:1200]} "
                    f"error={result.error} metadata={json.dumps(metadata, default=str)[:1200]}"
                )
