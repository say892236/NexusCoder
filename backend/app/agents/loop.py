"""驱动 Agent 持续执行的自主循环。

AgentLoop 本身不理解业务 Tool，只负责反复调用 ``BaseAgent.run()`` 并检查停止条件；
这让 Review、Summary 与 Coding Agent 可以复用同一套循环控制。
"""

import logging

from app.agents.base import AgentState, BaseAgent

logger = logging.getLogger(__name__)


class AgentLoop:
    """使用 ``run()`` 与 ``should_stop()`` 编排 Agent 生命周期。"""

    def __init__(self, agent: BaseAgent):
        """初始化 AgentLoop。

        Args:
            agent: 要执行的 BaseAgent 实例
        """
        self.agent = agent

    async def execute(self) -> AgentState:
        """持续执行 Agent，直到完成、失败或超过资源上限。

        Returns:
            最终 AgentState
        """
        logger.info(f"Starting agent loop for {self.agent.agent_id}")

        try:
            # 每轮先检查预算与终态，再执行一次 LLM/Tool Calling。
            while not self.agent.should_stop():
                # BaseAgent.run() 负责单轮模型调用和 Tool 执行。
                should_continue = await self.agent.run()

                # 完成 Tool 已产出结果时主动结束循环。
                if not should_continue:
                    break

        except Exception as e:
            logger.error(f"Agent loop failed: {e}", exc_info=True)
            self.agent.state.status = "failed"
            self.agent.state.error = str(e)

        # 统一记录最终状态及资源消耗，供监控与学习分析。
        logger.info(
            f"Agent {self.agent.agent_id} finished: "
            f"status={self.agent.state.status}, "
            f"iterations={self.agent.state.iteration}, "
            f"tokens={self.agent.state.tokens_used}, "
            f"tools={self.agent.state.tool_calls_made}"
        )

        return self.agent.state
