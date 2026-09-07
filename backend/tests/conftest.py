import asyncio
import sys

import pytest


@pytest.fixture
def event_loop_policy():
    """
    Windows 下 pytest-asyncio 默认可能使用 ProactorEventLoop。

    Psycopg 的异步连接要求 SelectorEventLoop，
    因此测试统一使用 SelectorEventLoopPolicy。
    """

    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()

    return asyncio.DefaultEventLoopPolicy()
