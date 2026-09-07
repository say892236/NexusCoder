import asyncio

from app.agents.implementation.background_agent import BackgroundAgent
from app.agents.loop import AgentLoop
from app.agents.sandbox.manager import SandboxManager
from app.agents.tools.manager import get_coder_tools
from app.core.client import get_llm_client


async def main():

    manager = SandboxManager()

    sandbox = manager.acquire(
        agent_id="coder-test",
        repository_url="https://github.com/pallets/flask.git",
        language="python",
    )


    tools = get_coder_tools(
        sandbox=sandbox
    )


    agent = BackgroundAgent(
        agent_id="coder",

        repository="pallets/flask",

        issue_number=1,

        issue_title="Add test file",

        issue_body="""
        Create a new file named agent_test.py.

        Content:

        print("hello from coding agent")
        """,

        custom_instructions="",

        tools=tools,

        llm_client=get_llm_client(),
    )


    result = await AgentLoop(agent).execute()


    print("================ result")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
