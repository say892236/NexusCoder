"""通过 Daytona SDK 在 Sandbox Runtime 中执行进程与命令的 Tool。"""

from app.agents.tools.base import BaseTool, ToolDefinition, ToolResult


class RunCommandTool(BaseTool):
    """在 Sandbox 中执行 shell 命令。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_command",
            description="Execute a shell command in the sandbox",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (default: workspace/repo)",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                    },
                },
                "required": ["command"],
            },
        )

    async def execute(
        self, command: str, cwd: str = "workspace/repo", timeout: int = 30, **kwargs
    ) -> ToolResult:
        """通过 ``Daytona process.exec()`` 执行命令。"""
        try:
            response = self.sandbox.process.exec(command=command, cwd=cwd, timeout=timeout)

            return ToolResult(
                success=response.exit_code == 0,
                data={"stdout": response.result, "exit_code": response.exit_code},
                metadata={"command": command},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class RunCodeTool(BaseTool):
    """直接执行 Python、TypeScript 或 JavaScript 代码。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_code",
            description="Execute code directly in the sandbox (Python, TypeScript, or JavaScript)",
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Code to execute"},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 30)",
                    },
                },
                "required": ["code"],
            },
        )

    async def execute(self, code: str, timeout: int = 30, **kwargs) -> ToolResult:
        """通过 ``Daytona process.code_run()`` 执行代码片段。"""
        try:
            response = self.sandbox.process.code_run(code)

            return ToolResult(
                success=response.exit_code == 0,
                data={"result": response.result, "exit_code": response.exit_code},
                metadata={"code_length": len(code)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class RunTestsTool(BaseTool):
    """运行 Repository 测试套件。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_tests",
            description="Run test suite (pytest, jest, etc.) in the repository",
            parameters={
                "type": "object",
                "properties": {
                    "test_path": {
                        "type": "string",
                        "description": "Path to test file or directory (default: . for all tests)",
                    },
                    "framework": {
                        "type": "string",
                        "enum": ["pytest", "jest", "unittest", "auto"],
                        "description": "Test framework to use (default: auto-detect)",
                    },
                },
                "required": [],
            },
        )

    async def execute(self, test_path: str = ".", framework: str = "auto", **kwargs) -> ToolResult:
        """通过 ``Daytona process.exec()`` 运行测试命令。"""
        try:
            # auto 模式当前使用 pytest 作为默认测试框架。
            if framework == "auto":
                framework = "pytest"  # 当前默认值。

            # 根据 framework 和测试路径拼装命令。
            if framework == "pytest":
                command = f"pytest {test_path} -v"
            elif framework == "jest":
                command = f"npm test -- {test_path}"
            elif framework == "unittest":
                command = f"python -m unittest discover {test_path}"
            else:
                command = f"{framework} {test_path}"

            response = self.sandbox.process.exec(
                command=command,
                cwd="workspace/repo",
                timeout=120,  # 测试通常比普通命令耗时更长。
            )

            return ToolResult(
                success=response.exit_code == 0,
                data={
                    "output": response.result,
                    "exit_code": response.exit_code,
                    "framework": framework,
                },
                metadata={"test_path": test_path},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class RunLinterTool(BaseTool):
    """运行 Repository 的代码 linter。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="run_linter",
            description="Run linter (ruff, eslint, etc.) to check code quality",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to lint (default: . for entire repo)",
                    },
                    "linter": {
                        "type": "string",
                        "enum": ["ruff", "eslint", "pylint", "auto"],
                        "description": "Linter to use (default: auto-detect)",
                    },
                },
                "required": [],
            },
        )

    async def execute(self, path: str = ".", linter: str = "auto", **kwargs) -> ToolResult:
        """通过 ``Daytona process.exec()`` 运行 lint 命令。"""
        try:
            if linter == "auto":
                linter = "ruff"  # auto 模式的当前默认值。

            # 根据 linter 和目标路径拼装命令。
            if linter == "ruff":
                command = f"ruff check {path}"
            elif linter == "eslint":
                command = f"npx eslint {path}"
            elif linter == "pylint":
                command = f"pylint {path}"
            else:
                command = f"{linter} {path}"

            response = self.sandbox.process.exec(command=command, cwd="workspace/repo", timeout=60)

            return ToolResult(
                success=response.exit_code == 0,
                data={
                    "output": response.result,
                    "exit_code": response.exit_code,
                    "linter": linter,
                },
                metadata={"path": path},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))
