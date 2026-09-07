from app.agents.sandbox.manager import SandboxManager


def main():
    print("🚀 创建 Daytona Sandbox")

    manager = SandboxManager()

    agent_id = "repo-test-001"

    try:
        sandbox = manager.acquire(
            agent_id=agent_id,
            repository_url="https://github.com/pallets/flask.git",
            language="python",
        )

        print("✅ Sandbox 创建成功")

        result = sandbox.process.exec(
            command="ls -la",
            cwd="workspace/repo",
            timeout=30,
        )

        print(result.result)

    finally:
        # 无论测试成功还是异常，都释放远程 Sandbox，
        # 避免留下资源继续占用。
        manager.release(agent_id)

        print("🧹 Sandbox 已释放")


if __name__ == "__main__":
    main()