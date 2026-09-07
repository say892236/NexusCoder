import json

LIST_FILES_STEP = 2
READ_FILE_STEP = 3
REPLACE_FILE_STEP = 4
RUN_TESTS_STEP = 5
GIT_ADD_STEP = 6
GIT_COMMIT_STEP = 7

RETRY_REPLACE_FILE_STEP = 9
RETRY_RUN_TESTS_STEP = 10
RETRY_GIT_ADD_STEP = 11
RETRY_GIT_COMMIT_STEP = 12
RETRY_FINISH_TASK_STEP = 13


class MockFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments




class MockToolCall:

    def __init__(self, call_id, name, arguments):

        self.id = call_id

        self.function = MockFunction(
            name,
            arguments
        )


class MockMessage:

    def __init__(
        self,
        content="",
        tool_calls=None
    ):

        self.content = content
        self.tool_calls = tool_calls or []


class MockChoice:

    def __init__(self, message):

        self.message = message


class MockResponse:

    def __init__(self, message):

        self.choices = [
            MockChoice(message)
        ]



class MockCompletion:
    def __init__(
        self,
        scenario: str = "success",
    ):
        # Coder AgentLoop 的步骤计数。
        self.step = 0

        # Evaluation 场景。
        self.scenario = scenario

        # Reviewer 独立计数，不能污染 Coder step。
        self.review_count = 0

    def create(self, **kwargs):
        # =====================================================
        # Memory Extractor
        # =====================================================
        # Memory 提炼不是 Coder AgentLoop 的一步，
        # 所以必须在 self.step += 1 之前处理，
        # 避免影响现有 Coder Mock 的步骤计数。
        messages = kwargs.get("messages", [])

        system_content = ""

        if messages:
            system_content = str(messages[0].get("content", ""))

        if "memory extraction component" in system_content:
            return MockResponse(
                MockMessage(
                    content=json.dumps(
                        {
                            "memories": [
                                {
                                    "memory_type": "SEMANTIC",
                                    "memory_key": "auth.user_field",
                                    "summary": ("Login logic uses the username field."),
                                    "content": (
                                        "Authentication code should read "
                                        "user['username'] instead of user['name']."
                                    ),
                                    "importance": 4,
                                },
                                {
                                    "memory_type": "EPISODIC",
                                    "memory_key": "auth.login_regression",
                                    "summary": ("Login changes should run focused tests."),
                                    "content": (
                                        "A previous login bug was caught and "
                                        "validated by running pytest."
                                    ),
                                    "importance": 3,
                                },
                            ]
                        },
                        ensure_ascii=False,
                    )
                )
            )
            # =====================================================
        # Reviewer
        # =====================================================

        tool_names = [tool["function"]["name"] for tool in kwargs.get("tools", [])]

        if "finish_review" in tool_names:
            self.review_count += 1

            # Evaluation 场景：
            # 第一次 Review 要求修改，第二次再通过。
            if self.scenario == "review_reject_once" and self.review_count == 1:
                return MockResponse(
                    MockMessage(
                        tool_calls=[
                            MockToolCall(
                                "review_001",
                                "finish_review",
                                json.dumps(
                                    {
                                        "summary": "发现问题，需要继续修改",
                                        "verdict": "REQUEST_CHANGES",
                                        "overall_severity": "medium",
                                    }
                                ),
                            )
                        ]
                    )
                )

            # 默认 Reviewer 通过。
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall(
                            f"review_{self.review_count:03d}",
                            "finish_review",
                            json.dumps(
                                {
                                    "summary": "代码检查通过",
                                    "verdict": "APPROVE",
                                    "overall_severity": "low",
                                }
                            ),
                        )
                    ]
                )
            )

        # =====================================================
        # Coder
        # =====================================================

        # 只有 Coder 调用才推进 Coder step。
        self.step += 1

        # 1. 创建修复分支
        if self.step == 1:
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall(
                            "call_001",
                            "git_create_branch",
                            json.dumps({"branch_name": "agent/fix-login"}),
                        )
                    ]
                )
            )

        # 2. 查看项目文件
        if self.step == LIST_FILES_STEP:
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall("call_002", "list_files", json.dumps({"directory": "."}))
                    ]
                )
            )

        # 3. 读取 app.py
        if self.step == READ_FILE_STEP:
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall("call_003", "read_file", json.dumps({"file_path": "app.py"}))
                    ]
                )
            )

        # 4. 修复真正的 Bug
        if self.step == REPLACE_FILE_STEP:
                # Tester Failure Evaluation：
            # 第一轮故意提交一个能够运行、
            # 但业务结果错误的实现，让 pytest 真正失败。
            if self.scenario in {
                "test_fail_once",
                "test_fail_always",
            }:
                replacement = (
                    '"username": '
                    'user.get("username", "") + "_wrong"'
                )
            else:
                # 默认正常修复。
                replacement = (
                    '"username": user["username"]'
                )

            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall(
                            "call_004",
                            "replace_in_files",
                            json.dumps(
                                {
                                    "files": ["app.py"],
                                    "pattern": (
                                        '"username": user["name"]'
                                    ),
                                    "replacement": replacement,
                                }
                            ),
                        )
                    ]
                )
            )

        # 5. 执行测试
        if self.step == RUN_TESTS_STEP:
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall("call_005", "run_command", json.dumps({"command": "pytest"}))
                    ]
                )
            )

        # 6. 暂存真正修改的业务文件
        if self.step == GIT_ADD_STEP:
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall("call_006", "git_add", json.dumps({"files": ["app.py"]}))
                    ]
                )
            )

        # 7. Commit
        if self.step == GIT_COMMIT_STEP:
            return MockResponse(
                MockMessage(
                    tool_calls=[
                        MockToolCall(
                            "call_007",
                            "git_commit",
                            json.dumps({"message": "fix: resolve login endpoint 500 error"}),
                        )
                    ]
                )
            )

                # =========================================================


        # Evaluation: Tester 第一次失败后，第二轮 Coder 修复
        # =========================================================

        if self.scenario == "test_fail_once":
            # Retry Coder 第 1 步：
            # 根据上一轮 Tester Feedback 修正错误实现。
            if self.step == RETRY_REPLACE_FILE_STEP:
                return MockResponse(
                    MockMessage(
                        tool_calls=[
                            MockToolCall(
                                "retry_call_001",
                                "replace_in_files",
                                json.dumps(
                                    {
                                        "files": ["app.py"],
                                        "pattern": ('"username": user.get("username", "") + "_wrong"'),
                                        "replacement": ('"username": user["username"]'),
                                    }
                                ),
                            )
                        ]
                    )
                )

            # Retry Coder 第 2 步：重新测试。
            if self.step == RETRY_RUN_TESTS_STEP:
                return MockResponse(
                    MockMessage(
                        tool_calls=[
                            MockToolCall(
                                "retry_call_002",
                                "run_command",
                                json.dumps(
                                    {
                                        "command": "pytest",
                                    }
                                ),
                            )
                        ]
                    )
                )

            # Retry Coder 第 3 步：暂存修复。
            if self.step == RETRY_GIT_ADD_STEP:
                return MockResponse(
                    MockMessage(
                        tool_calls=[
                            MockToolCall(
                                "retry_call_003",
                                "git_add",
                                json.dumps(
                                    {
                                        "files": ["app.py"],
                                    }
                                ),
                            )
                        ]
                    )
                )

            # Retry Coder 第 4 步：提交修复。
            if self.step == RETRY_GIT_COMMIT_STEP:
                return MockResponse(
                    MockMessage(
                        tool_calls=[
                            MockToolCall(
                                "retry_call_004",
                                "git_commit",
                                json.dumps(
                                    {
                                        "message": ("fix: address failing login test"),
                                    }
                                ),
                            )
                        ]
                    )
                )

            # Retry Coder 第 5 步：重新完成任务。
            if self.step == RETRY_FINISH_TASK_STEP:
                return MockResponse(
                    MockMessage(
                        tool_calls=[
                            MockToolCall(
                                "retry_call_005",
                                "finish_task",
                                json.dumps(
                                    {
                                        "summary": ("根据测试失败信息修正登录字段返回值"),
                                        "branch_name": ("agent/fix-login"),
                                    }
                                ),
                            )
                        ]
                    )
                )

        # 8. 完成 Coding Task
        return MockResponse(
            MockMessage(
                tool_calls=[
                    MockToolCall(
                        "call_008",
                        "finish_task",
                        json.dumps(
                            {
                                "summary": "修复正确账号密码登录时因错误访问 user['name'] 导致的500错误",
                                "branch_name": "agent/fix-login",
                            }
                        ),
                    )
                ]
            )
        )
class MockChat:
    def __init__(
        self,
        scenario: str = "success",
    ):
        self.completions = MockCompletion(
            scenario=scenario,
        )


class MockLLM:
    def __init__(
        self,
        scenario: str = "success",
    ):
        self.chat = MockChat(
            scenario=scenario,
        )
