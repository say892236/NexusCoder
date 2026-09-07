import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
from pathlib import Path


class MockResult:
    """
    模拟 Daytona command 执行结果
    """

    def __init__(self, code=0, output=""):
        self.exit_code = code
        self.result = output


# ===============================
# Mock File System
# ===============================


class MockFileSystem:
    def __init__(
        self,
        fixture: str = "login_500",
    ):
        # 每次创建 MockSandbox 都使用全新的临时目录，
        # 避免上一次测试留下的 Git / 文件状态污染下一次测试。
        self.base = Path(tempfile.mkdtemp(prefix="metis_mock_"))

        self.root = self.base / "workspace" / "repo"

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        # fixture 决定当前 Sandbox 初始化哪一套代码仓库。
        self.fixture = fixture

        self._create_demo_project()

    def _create_demo_project(self):
        """根据 fixture 创建对应的评测仓库。"""

        builders = {
            "login_500": self._create_login_500_project,
            "empty_average": self._create_empty_average_project,
        }

        builder = builders.get(self.fixture)

        if builder is None:
            raise ValueError(f"Unknown MockSandbox fixture: {self.fixture}")

        builder()

    def _create_login_500_project(self):
        """
        创建一个简单的登录接口项目。
        给 Coding Agent 测试修改代码使用。
        """

        app_py = textwrap.dedent(
            """
            from flask import Flask, request, jsonify


            app = Flask(__name__)


            USERS = {
                "admin": {
                    "username": "admin",
                    "password": "123456"
                }
            }


            @app.route("/login", methods=["POST"])
            def login():

                data = request.get_json() or {}

                username = data.get("username")
                password = data.get("password")

                user = USERS.get(username)

                if user and user["password"] == password:

                    # 故意制造 Bug：
                    # user 中没有 name 字段，正确登录时会触发 KeyError，
                    # Flask 最终返回 500。
                    return jsonify({
                        "username": user["name"]
                    })

                return jsonify({
                    "message": "invalid credentials"
                }), 401


            if __name__ == "__main__":
                app.run()
            """
        )

        test_py = textwrap.dedent(
            """
            from app import app


            def test_login_success():

                client = app.test_client()

                response = client.post(
                    "/login",
                    json={
                        "username": "admin",
                        "password": "123456"
                    }
                )

                assert response.status_code == 200
                assert response.get_json()["username"] == "admin"
            """
        )

        readme = textwrap.dedent("""
    # Demo Login API


    ## Problem

    Login API may return 500 error.


    ## Files

    app.py
    test_app.py
    """)

        self.write_file("app.py", app_py)

        self.write_file("test_app.py", test_py)

        self.write_file("README.md", readme)

        gitignore = textwrap.dedent(
            """
            __pycache__/
            .pytest_cache/
            .coverage
            htmlcov/
            """
        )

        self.write_file(".gitignore", gitignore)

    def _normalize_path(self, path):

        if isinstance(path, bytes):
            path = path.decode()

        path = str(path).replace("\\", "/")

        prefixes = [
            "workspace/repo/",
            "workspace/repo",
            "./workspace/repo/",
            "./workspace/repo",
        ]

        for prefix in prefixes:
            if path.startswith(prefix):
                path = path[len(prefix) :]
                break

        return Path(path)

    def _create_empty_average_project(self):
        """创建空列表计算平均值时发生除零错误的评测仓库。"""

        stats_py = textwrap.dedent(
            """
            def calculate_average(values):
                \"\"\"计算数字列表的平均值。\"\"\"

                total = sum(values)

                # Bug：
                # values 为空列表时 len(values) == 0，
                # 会触发 ZeroDivisionError。
                return total / len(values)
            """
        )

        test_py = textwrap.dedent(
            """
            from stats import calculate_average


            def test_average_normal():
                assert calculate_average([10, 20, 30]) == 20


            def test_average_empty():
                assert calculate_average([]) == 0
            """
        )

        readme = textwrap.dedent(
            """
            # Statistics Demo


            ## Problem

            The average calculation crashes when the input list is empty.


            ## Expected Behavior

            - Normal numeric lists should return their average.
            - An empty list should return 0.


            ## Files

            stats.py
            test_stats.py
            """
        )

        gitignore = textwrap.dedent(
            """
            __pycache__/
            .pytest_cache/
            .coverage
            htmlcov/
            """
        )

        self.write_file("stats.py", stats_py)
        self.write_file("test_stats.py", test_py)
        self.write_file("README.md", readme)
        self.write_file(".gitignore", gitignore)

    def upload_file(self, path, content):

        if isinstance(content, bytes):
            content = content.decode()

        file_path = self.root / self._normalize_path(path)

        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding="utf-8")

    def download_file(self, path):

        file_path = self.root / self._normalize_path(path)

        if not file_path.exists():
            return ""

        return file_path.read_text(encoding="utf-8")

    def write_file(self, path, content):

        self.upload_file(path, content)

    def read_file(self, path):

        return self.download_file(path)

    def delete_file(self, path):

        file_path = self.root / self._normalize_path(path)

        if file_path.exists():
            file_path.unlink()

    def list_files(self, directory="."):
        """只列出指定目录的直接子项，不递归遍历整个目录树。"""

        base = self.root / self._normalize_path(directory)

        class MockFile:
            def __init__(self, path):
                self.name = path.name
                self.is_dir = path.is_dir()

                self.size = path.stat().st_size if path.is_file() else 0

                self.path = str(path)

        # 只读取当前目录这一层。
        # 同时固定排序，保证 Tool 输出稳定。
        return [
            MockFile(path)
            for path in sorted(
                base.iterdir(),
                key=lambda item: item.name.lower(),
            )
        ]

    def search_files(self, pattern, path="."):

        results = []

        base = self.root / self._normalize_path(path)

        for file in base.rglob("*"):
            if file.is_file():
                text = file.read_text(encoding="utf-8")

                if pattern in text:
                    results.append(str(file))

        return results

    def replace_in_files(self, files, pattern=None, replacement=None, new_value=None):

        if replacement is None:
            replacement = new_value

        for file in files:
            file_path = self.root / self._normalize_path(file)

            text = file_path.read_text(encoding="utf-8")

            text = text.replace(pattern, replacement)

            file_path.write_text(text, encoding="utf-8")

    def find_files(self, pattern, path="."):

        return self.search_files(pattern, path)


# ===============================
# Mock Process
# ===============================


class MockProcess:
    def __init__(self, root):
        self.root = root

    def exec(self, command, cwd=None, timeout=None):

        cwd_path = self.root

        env = os.environ.copy()

        # MockSandbox 中执行 pytest 时，
        # 不自动加载 backend 虚拟环境里的第三方 pytest 插件。
        #
        # 这些临时评测仓库只需要 pytest 核心功能，
        # 禁用插件自动加载可以减少启动开销，并避免 LangSmith 等
        # 宿主项目插件干扰 Sandbox 内部测试。
        if command.strip().startswith("pytest"):
            env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"

        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd_path,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        print("🛠 Mock执行:", command)
        print("================")
        print(stdout)
        print(stderr)
        print("================")

        return MockResult(
            result.returncode,
            stdout + stderr,
        )


# ===============================
# Mock Git
# ===============================


class MockGit:
    """
    不模拟git状态

    直接调用真实git命令
    """

    def __init__(self, root):

        self.root = root

        self.init_repo()

    def run_git(self, cmd):

        result = subprocess.run(cmd, cwd=self.root, shell=True, capture_output=True, text=True)

        return result.stdout.strip()

    def init_repo(self):

        git_dir = self.root / ".git"

        if not git_dir.exists():
            subprocess.run("git init -b main", cwd=self.root, shell=True)

            subprocess.run('git config user.name "Mock Agent"', cwd=self.root, shell=True)

            subprocess.run('git config user.email "mock@test.com"', cwd=self.root, shell=True)

            # 创建初始提交
            subprocess.run("git add .", cwd=self.root, shell=True)

            subprocess.run('git commit -m "initial commit"', cwd=self.root, shell=True)

    def status(self, path=None):

        branch = self.run_git("git branch --show-current")

        diff = self.run_git("git status --short")

        return type(
            "Status",
            (),
            {
                "current_branch": branch,
                "file_status": diff,
                "ahead": 0,
                "behind": 0,
                "modified": [],
                "untracked": [],
            },
        )()

    def branches(self, path=None):

        result = self.run_git("git branch --format='%(refname:short)'")

        return type("Branches", (), {"branches": result.splitlines()})()

    def create_branch(self, path, branch_name):
        """
        模拟 Daytona git.create_branch(path, branch_name)。

        path 参数为了与 Daytona API 保持一致；
        Mock 环境本身已经绑定 self.root，因此不需要实际使用 path。
        """

        exists = self.run_git(f"git branch --list {branch_name}")

        if exists:
            subprocess.run(f"git checkout {branch_name}", cwd=self.root, shell=True)
        else:
            subprocess.run(f"git checkout -b {branch_name}", cwd=self.root, shell=True)

        return True

    def checkout_branch(self, branch_name, path=None):

        subprocess.run(f"git checkout {branch_name}", cwd=self.root, shell=True)

    def add(self, files, path=None):

        subprocess.run("git add .", cwd=self.root, shell=True)

        return True

    def commit(self, message, path=None):

        subprocess.run("git add .", cwd=self.root, shell=True)

        subprocess.run(f'git commit -m "{message}"', cwd=self.root, shell=True)

        return True

    def push(self, path=None):

        print("mock git push")

        return True

    def pull(self, path=None):

        subprocess.run("git pull", cwd=self.root, shell=True)

        return True


# ===============================
# Mock Sandbox
# ===============================


class MockSandbox:
    def __init__(
        self,
        fixture: str = "login_500",
    ):
        # 保存当前 fixture，方便 Evaluation 和调试查看。
        self.fixture = fixture

        self.fs = MockFileSystem(
            fixture=fixture,
        )

        self.process = MockProcess(
            self.fs.root,
        )

        self.git = MockGit(
            self.fs.root,
        )

    def start(self):

        print("Mock sandbox start")

    def stop(self):

        print("Mock sandbox stop")

    def delete(self):
        """删除 Mock Sandbox 对应的临时工作目录。"""

        if not self.fs.base.exists():
            return

        def handle_remove_error(func, path, exc):
            """
            Windows 下 .git 中部分文件可能带只读属性，
            删除失败时先赋予写权限，再重试。
            """
            Path(path).chmod(stat.S_IWRITE)
            func(path)

        shutil.rmtree(
            self.fs.base,
            onexc=handle_remove_error,
        )

        print("Mock sandbox delete")
