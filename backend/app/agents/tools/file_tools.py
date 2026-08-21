"""通过 Daytona SDK 操作 Sandbox 文件系统的 Tool。"""

from app.agents.tools.base import BaseTool, ToolDefinition, ToolResult


class ReadFileTool(BaseTool):
    """读取 Sandbox 文件内容。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_file",
            description="Read the contents of a file from the repository",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to file relative to workspace/repo",
                    }
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, file_path: str, **kwargs) -> ToolResult:
        """通过 ``Daytona fs.download_file()`` 执行文件读取。"""
        try:
            # 相对路径统一解析到 Sandbox 内 clone 后的 Repository 根目录。
            if not file_path.startswith("/") and not file_path.startswith("workspace/"):
                file_path = f"workspace/repo/{file_path}"

            # Daytona 返回字节内容，再由 Tool 转成 LLM 可消费的文本。
            content = self.sandbox.fs.download_file(file_path)

            # 使用 UTF-8 解码 Repository 文本文件。
            if isinstance(content, bytes):
                content = content.decode("utf-8")

            return ToolResult(
                success=True,
                data={"content": content, "path": file_path},
                metadata={"size_bytes": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListFilesTool(BaseTool):
    """列出 Sandbox 中的文件和目录。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_files",
            description="List files and directories in a path",
            parameters={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Directory path (default: workspace/repo)",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, directory: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona fs.list_files()`` 执行目录遍历。"""
        try:
            # 相对路径统一从 Repository 根目录开始。
            if not directory.startswith("/") and not directory.startswith("workspace/"):
                directory = f"workspace/repo/{directory}"

            files = self.sandbox.fs.list_files(directory)

            # 精简 SDK 对象，只返回 Agent 判断下一步所需的字段。
            file_list = [
                {
                    "name": f.name,
                    "is_dir": f.is_dir,
                    "size": f.size,
                    "modified": str(f.mod_time) if hasattr(f, "mod_time") else None,
                }
                for f in files
            ]

            return ToolResult(
                success=True,
                data={"files": file_list, "directory": directory},
                metadata={"count": len(file_list)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class SearchFilesTool(BaseTool):
    """在 Sandbox 文件中搜索文本，作用类似 grep。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_files",
            description="Search for text patterns in files (recursive grep)",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to search in (default: workspace/repo)",
                    },
                },
                "required": ["pattern"],
            },
        )

    async def execute(self, pattern: str, path: str = "workspace/repo", **kwargs) -> ToolResult:
        """通过 ``Daytona fs.find_files()`` 执行搜索。"""
        try:
            # 相对路径自动补全为 Repository 工作目录。
            if not path.startswith("/") and not path.startswith("workspace/"):
                path = f"workspace/repo/{path}"

            # 搜索实际在远程 Sandbox 中执行，不读取宿主机文件。
            results = self.sandbox.fs.find_files(path=path, pattern=pattern)

            # 将 SDK 搜索结果转换为稳定的 ToolResult 数据。
            matches = [
                {"file": match.file, "line": match.line, "content": match.content}
                for match in results
            ]

            return ToolResult(
                success=True,
                data={"matches": matches, "pattern": pattern},
                metadata={"match_count": len(matches)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ReplaceInFilesTool(BaseTool):
    """替换 Sandbox 文件中的文本。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="replace_in_files",
            description="Replace text in one or more files",
            parameters={
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of file paths to modify",
                    },
                    "pattern": {
                        "type": "string",
                        "description": "Text pattern to find",
                    },
                    "replacement": {
                        "type": "string",
                        "description": "Text to replace with",
                    },
                },
                "required": ["files", "pattern", "replacement"],
            },
        )

    async def execute(
        self, files: list[str], pattern: str, replacement: str, **kwargs
    ) -> ToolResult:
        """通过 ``Daytona fs.replace_in_files()`` 执行文本替换。"""
        try:
            # 仅对相对路径补全 Repository 前缀，绝对路径保持原样。
            full_paths = [f"workspace/repo/{f}" if not f.startswith("/") else f for f in files]

            self.sandbox.fs.replace_in_files(
                files=full_paths, pattern=pattern, new_value=replacement
            )

            return ToolResult(
                success=True,
                data={
                    "files_modified": full_paths,
                    "pattern": pattern,
                    "replacement": replacement,
                },
                metadata={"file_count": len(full_paths)},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class CreateFileTool(BaseTool):
    """在 Sandbox 中创建新文件。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="create_file",
            description="Create a new file with content",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path for new file relative to workspace/repo",
                    },
                    "content": {"type": "string", "description": "File content"},
                },
                "required": ["file_path", "content"],
            },
        )

    async def execute(self, file_path: str, content: str, **kwargs) -> ToolResult:
        """通过 ``Daytona fs.upload_file()`` 上传内容并创建文件。"""
        try:
            full_path = f"workspace/repo/{file_path}"
            self.sandbox.fs.upload_file(content.encode("utf-8"), full_path)

            return ToolResult(
                success=True,
                data={"path": file_path, "size": len(content)},
                metadata={"created": True},
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class DeleteFileTool(BaseTool):
    """删除 Sandbox 中的文件。"""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="delete_file",
            description="Delete a file from the repository",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to file relative to workspace/repo",
                    }
                },
                "required": ["file_path"],
            },
        )

    async def execute(self, file_path: str, **kwargs) -> ToolResult:
        """通过 ``Daytona fs.delete_file()`` 执行文件删除。"""
        try:
            full_path = f"workspace/repo/{file_path}"
            self.sandbox.fs.delete_file(full_path)

            return ToolResult(success=True, data={"path": file_path, "deleted": True})
        except Exception as e:
            return ToolResult(success=False, error=str(e))
