# Metis 项目全景说明

> 扫描日期：2026-08-19  
> 本文只做现状梳理，不代表已经修改、重构或验证了业务运行结果。

## 先用一句话理解 Metis

Metis 目前首先是一个 **GitHub App 形态的 AI Code Review 平台**，同时已经包含一条可用雏形的 **GitHub Issue → Coding Agent → Pull Request** 流程。

如果要把它二次开发成“面向企业研发工单的 Coding Agent Runtime”，最有价值的不是现有的宣传页或 Review Dashboard，而是下面这条主干：

```text
工单上下文
  → 创建可追踪的 AgentRun
  → 异步任务调度
  → 创建隔离 Sandbox
  → LLM 循环调用工具
  → 修改文件 / 执行命令 / 运行测试 / Git 操作
  → 产出分支与 Pull Request
```

当前代码已经把这条主干的大部分零件放好了，但它仍然是“GitHub 专用应用”，还不是通用、可靠、可暂停、可审批、可恢复的企业级 Agent Runtime。

## 扫描范围与边界

本次检查了 Git 跟踪的根目录文件、配置、Backend、Frontend、数据库迁移、Docker Compose、GitHub Actions，以及 `backend/app` 的全部 Python 文件结构和关键实现。

- Git 跟踪文件：约 204 个。
- `backend/app`：71 个 Python 文件，约 9,360 行。
- `frontend/src`：73 个源码文件，约 9,185 行。
- `backend/tests`：当前只有一个空的 `__init__.py`，实际上没有测试用例。
- 本地存在未跟踪的 `backend/.idea/`，它属于用户工作区内容，本次没有读取或修改。
- 本地 `backend/.venv/` 是开发环境产物，不属于 Git 跟踪源码，不纳入项目代码分析。

### 关于 `daytona/`

`daytona/` 不是 Metis 自己维护的目录，而是一个 Git submodule：

- 上游：`https://github.com/daytonaio/daytona.git`
- 当前固定提交：`847f154bcb9dbba11c31d173f3f40b1f22502556`
- 当前工作区没有初始化 submodule，所以目录为空，无法对该固定提交做本地逐文件审计。
- Metis 实际运行时通过 `backend/pyproject.toml` 中的 Python 包 `daytona>=0.125.0` 使用 Daytona SDK。
- Metis 自己真正需要理解的适配代码在 `backend/app/agents/sandbox/client.py` 和 `manager.py`。

这意味着：如果后续不准备自托管 Daytona，根目录 submodule 很可能不是运行必需项；但 Daytona SDK 适配层仍然是 Coding Agent Runtime 的核心。

## 业务背景

Metis 面向使用 GitHub 协作的研发团队，当前有两条相互独立但共用 Agent Runtime 的业务线。

### 业务线一：自动 PR Review

GitHub App 收到 Pull Request webhook 后：

1. 校验 webhook 签名。
2. 在 PostgreSQL 创建 `Review`。
3. 通过 Celery 并行投递 Review Agent 和 Summary Agent。
4. 在 Daytona Sandbox 中克隆 PR 分支。
5. Agent 阅读代码、执行测试和 Linter，并把发现逐条发到 GitHub。
6. 最后发布整体 Review，并可更新 PR 标题和描述。

这是项目最早、最完整的产品主线。

### 业务线二：Issue 到 PR

用户登录 Dashboard，选择一个已接入的仓库，打开 GitHub Issue，然后手动点击 “Code with agent mode”。系统会：

1. 创建 `AgentRun`。
2. 投递后台 Coding Agent。
3. 在隔离环境里克隆仓库。
4. 让 Agent 建分支、修改文件、运行测试、提交并 Push。
5. Backend 验证远端分支存在。
6. Backend 调 GitHub API 创建 Pull Request。

这条链最接近后续的“企业研发工单 Coding Agent Runtime”。

## 它解决了什么问题

- 把高延迟、资源消耗大的 LLM 编码任务从 HTTP 请求中拆到异步 Worker。
- 让 AI 生成和执行的代码处于 Daytona 隔离环境，而不是直接运行在 Backend 主机。
- 给 Agent 一套结构化工具，而不是只让模型输出一段自然语言或代码片段。
- 用 PostgreSQL 保存 Review、AgentRun、工具对话和 PR 结果，便于前端查询。
- 用 GitHub App installation token 访问多个仓库，不要求每个仓库单独配置个人 Token。
- 通过 LiteLLM 统一不同模型供应商的调用接口。

## 当前核心功能

### 已有实现

- GitHub OAuth 登录和 HTTP-only Cookie 会话。
- GitHub App installation 与多仓库接入。
- 仓库级 Review 灵敏度、自定义指令和忽略规则。
- PR webhook 自动 Review。
- PR 描述和标题的 AI Summary。
- GitHub Issue 列表、详情和评论读取。
- 从 Issue 手动启动 Coding Agent。
- Agent 文件、Shell、Git、测试、Linter 工具。
- Daytona Sandbox 创建、克隆和销毁。
- AgentRun 状态、Token、工具调用、对话和 PR 结果持久化。
- Dashboard、Review 结果、Analytics、Issue 与 Agent 运行详情页面。

### README 容易让人误解的地方

- “实时进度”目前是前端每 3 秒轮询 PostgreSQL 查询接口，不是 WebSocket、SSE 或 Redis Stream。
- Coding Agent 运行期间并不会持续写入 iteration、conversation 和 tool trace；这些字段主要在 Agent Loop 结束后一次性写入。
- `core/redis_client.py` 当前没有被其他业务代码调用。Issue → PR 链中的 Redis 使用来自 Celery broker/result backend。
- `docker-compose.dev.yml` 没有 Redis Insight 服务，虽然根 README 的 Quick Start 仍然写了 Redis Insight。
- Backend CI 当前执行 Ruff、格式检查和 MyPy，但没有执行 Pytest；仓库也没有实际测试用例。
- Issue → PR 不是 Issue webhook 触发，而是登录用户从前端或 API 手动启动。

## 技术栈

| 层次 | 当前技术 | 用途 |
|---|---|---|
| Backend API | Python 3.10+、FastAPI | HTTP API、OAuth、Webhook、查询 AgentRun |
| 数据访问 | SQLAlchemy 2 Async、asyncpg | PostgreSQL 异步 ORM |
| 数据库迁移 | Alembic | 表结构版本管理 |
| 异步任务 | Celery 5 | Review、Summary、Coding Agent 后台任务 |
| 消息系统 | Redis 7 | Celery broker 和 result backend |
| LLM | LiteLLM | 统一 Vertex AI、OpenAI、Anthropic、Mistral 等模型接口 |
| Agent Runtime | 自研 `BaseAgent`、`AgentLoop`、`ToolManager` | LLM 与工具循环 |
| 隔离执行 | Daytona Python SDK | Sandbox、文件系统、进程和 Git 操作 |
| GitHub 集成 | GitHub App、OAuth、httpx、JWT | 仓库授权、Issue、PR、Review、评论 |
| Frontend | React 19、TypeScript、React Router | Dashboard 与 Agent 运行页面 |
| UI | Tailwind CSS v4、shadcn/ui、Radix UI | Neo-brutalist 风格组件 |
| 构建 | Vite 的 Rolldown 分支、pnpm | Frontend 开发和打包 |
| 可观测性 | LangSmith、文件日志、Celery 日志 | LLM Trace 和任务日志 |
| 容器 | Docker、Docker Compose、Nginx | 本地开发和部署 |
| CI/CD | GitHub Actions、Google Artifact Registry、Cloud Run | 质量检查、镜像构建和部署 |

## 整体架构

```text
┌──────────────────────┐
│ GitHub               │
│ OAuth / App / Issue  │
│ PR / Webhook         │
└──────────┬───────────┘
           │ HTTPS
           ▼
┌─────────────────────────────────────────────┐
│ FastAPI                                    │
│ api → services → repositories/models       │
│ 创建 Review / AgentRun，查询运行结果        │
└──────────┬───────────────────┬──────────────┘
           │ SQLAlchemy        │ Celery.delay()
           ▼                   ▼
┌──────────────────┐   ┌──────────────────────┐
│ PostgreSQL       │   │ Redis                │
│ User             │   │ DB 0: broker         │
│ Installation     │   │ DB 1: result backend │
│ Review/Comment   │   └──────────┬───────────┘
│ AgentRun         │              │
└────────▲─────────┘              ▼
         │               ┌─────────────────────┐
         │               │ Celery Worker       │
         │               │ tasks/*             │
         │               └──────┬───────┬──────┘
         │                      │       │
         │              LiteLLM│       │Daytona SDK
         │                      ▼       ▼
         │                ┌────────┐ ┌──────────────┐
         │                │ LLM    │ │ Sandbox      │
         │                └────────┘ │ File/Shell   │
         │                           │ Git/Test     │
         │                           └──────┬───────┘
         │                                  │ push branch
         └──────────────────────────────────┴──→ GitHub PR

React Frontend ──Cookie Auth──→ FastAPI
React Frontend ──每 3 秒轮询──→ GET /api/agents/{id}
```

## 根目录职责

| 路径 | 职责 | 初期关注度 |
|---|---|---|
| `backend/` | FastAPI、Celery、Agent、数据库和 GitHub 集成 | 最高 |
| `frontend/` | 登录、仓库管理、Review、Issue、AgentRun Dashboard | 中高 |
| `daytona/` | 外部 Daytona 源码 submodule，本地未初始化 | 暂不读源码 |
| `docker-compose.dev.yml` | PostgreSQL、Redis、pgAdmin、API、Worker、Frontend 本地编排 | 高 |
| `README.md` | 英文项目总览和启动说明 | 高，但需和代码交叉核对 |
| `backend/README.md` | 非常详细的 Backend 说明 | 中高，部分内容可能比代码超前或滞后 |
| `frontend/README.md` | Frontend 页面和组件说明 | 中 |
| `Makefile` | 开发、构建、Lint、迁移和测试命令入口 | 中 |
| `.github/workflows/` | CI、安全扫描、GCP 镜像构建和 Cloud Run 部署 | 需要部署时再看 |
| `static/` | README 和品牌静态资源 | 低 |
| `.claude/CLAUDE.md` | 给其他 Coding Agent 的项目说明和约定 | 可参考，不是运行时代码 |
| `CONTRIBUTING.md`、`SECURITY.md` | 开源协作和安全报告规范 | 接手治理时看 |

## `backend/app` 心智模型

### `api/`：HTTP 入口

只负责接收参数、认证、权限边界、返回 Schema，以及调用下一层。

- `agents.py`：创建和查询 Issue Coding Agent 的 `AgentRun`。
- `issues.py`：从 GitHub 动态读取 Issue 和评论；Issue 本身不落库。
- `webhooks.py`：接收 GitHub webhook。
- `auth.py`：GitHub OAuth 登录、刷新和退出。
- `installations.py`：同步、启用、配置和停用仓库。
- `review_comments.py`：查询 Review Agent 生成的逐行问题。
- `analytics.py`：聚合 Review 和 ReviewComment 指标。

### `agents/`：真正的 Agent Runtime

这是未来二次开发的核心。

- `base.py`
  - `AgentState` 保存一次运行的内存状态。
  - `BaseAgent.run()` 完成一次 LLM → tool calls → tool results 循环。
  - `BaseAgent.should_stop()` 检查迭代、Token、工具次数和时长上限。
- `loop.py`
  - `AgentLoop.execute()` 反复调用 `run()`，直到完成或触发限制。
- `implementation/`
  - `BackgroundAgent`：Issue → PR。
  - `ReviewAgent`：PR Code Review。
  - `SummaryAgent`：PR 标题和描述摘要。
- `prompts/`
  - 三种 Agent 的硬编码 System Prompt 和初始任务上下文。
- `tools/`
  - 工具协议、注册、Schema 生成、批量执行。
  - 文件、进程、测试、Linter、Git、Review 发布、结束任务工具。
- `sandbox/`
  - Daytona SDK 初始化、Sandbox 创建、克隆和生命周期管理。

### `tasks/`：长任务编排

Celery Worker 的业务入口。它们负责把数据库、GitHub、Sandbox、Agent 和最终副作用串起来。

- `background_agent_task.py`：Issue → PR 主流程。
- `agent_review_task.py`：PR Review 主流程。
- `summary_task.py`：PR Summary 主流程。

目前三个 Task 都比较“胖”，既做状态机、外部 API、Sandbox、Agent，也做失败处理和清理。未来最值得拆的是这一层，而不是先拆 `BaseAgent`。

### `services/`：外部系统和业务服务

- `github.py`：GitHub App JWT、installation token、Issue、PR、Review、评论接口。
- `oauth.py`：GitHub OAuth。
- `webhook.py`：PR webhook 业务分发。
- `pr_summary.py`：把 AI Summary 合入现有 PR 描述。

### `repositories/`：数据库访问封装

- `installation.py`、`review.py`、`user.py` 分别封装对应实体的 CRUD 和查询。
- `AgentRun` 目前没有 Repository 类，`api/agents.py`、`api/issues.py` 和 `background_agent_task.py` 直接写 SQLAlchemy 查询。这是当前分层不一致点。

### `models/`：PostgreSQL ORM

- `User`：GitHub OAuth 用户和加密 Token。
- `Installation`：用户、GitHub App installation、仓库和 Review 配置。
- `Review`：一次 PR Review。
- `ReviewComment`：一条文件或行级问题。
- `AgentRun`：一次 Issue Coding Agent 执行及完整 Trace。

关系可以简化为：

```text
User 1 ── N Installation 1 ── N Review 1 ── N ReviewComment
User 1 ── N AgentRun
Installation 1 ── N AgentRun
```

`AgentRun` 同时引用 `User` 和 `Installation`，但不引用 `Review`，因为 Coding Agent 与 PR Review 是两条独立业务线。

### `schemas/`：API 数据契约

Pydantic Request/Response，包括 AgentRun、Issue、Installation、Analytics、ReviewComment 和 Review 配置。

需要注意：`frontend/src/types/api.ts` 的 `Issue` 类型仍保留了旧字段，如 `github_issue_id`、`issue_id`；Backend 当前返回的是 GitHub 原始数值 `id` 和 `github_url`。这属于前后端契约漂移，应在后续开发前用契约测试锁定。

### `db/`：数据库基础设施

- `base.py`：Async Engine、`AsyncSessionLocal` 和 Declarative Base。
- `session.py`：FastAPI 请求级 Session，成功自动 commit，失败 rollback。
- `base_class.py`：UUID、创建时间和更新时间公共字段。

### `core/`：全局基础设施

- `config.py`：Pydantic Settings 和环境变量。
- `celery_app.py`：Celery、重试、ACK、时限和任务注册。
- `client.py`：LiteLLM 的 OpenAI-compatible 适配器。
- `security.py`：JWT 和 Token 加解密。
- `auth_deps.py`：当前用户依赖。
- `redis_client.py`：异步 Redis Singleton；当前未被业务代码使用。

### `utils/`：辅助代码

- Agent 文件日志。
- Prompt 辅助函数。

## 最重要的完整调用链：GitHub Issue → Pull Request

### 先明确触发方式

当前链路不是由 GitHub Issue webhook 自动触发。真实入口是：

```text
IssueDetailPage 点击按钮
→ apiClient.launchAgent()
→ POST /api/agents/launch
```

GitHub Issue 只是任务上下文来源。

### 逐步映射到代码

| 步骤 | 发生了什么 | Python 文件 | 核心类 / 函数 |
|---|---|---|---|
| 1 | Frontend 读取 GitHub Issue | `backend/app/api/issues.py` | `get_issue()`、`list_issues()` |
| 2 | Backend 调 GitHub Issue API | `backend/app/services/github.py` | `GitHubService.get_issue()`、`get_repository_issues()` |
| 3 | 用户请求启动 Agent | `backend/app/api/agents.py` | `launch_agent()` |
| 4 | 校验当前用户拥有且启用了仓库 | `backend/app/api/agents.py` | `launch_agent()` 查询 `Installation` |
| 5 | 再次读取 Issue 快照 | `backend/app/services/github.py` | `GitHubService.get_issue()` |
| 6 | PostgreSQL 创建 `AgentRun(PENDING)` | `backend/app/models/agent_run.py`、`backend/app/api/agents.py` | `AgentRun`、`db.add()`、`db.flush()` |
| 7 | 向 Redis broker 投递 Celery 消息 | `backend/app/api/agents.py` | `process_issue_with_agent.delay()` |
| 8 | Celery Worker 找到任务 | `backend/app/core/celery_app.py` | `celery_app`、末尾的任务模块导入 |
| 9 | 同步 Celery Task 进入 async 主流程 | `backend/app/tasks/background_agent_task.py` | `process_issue_with_agent()` → `asyncio.run(_process_issue_with_agent_async())` |
| 10 | 从 PostgreSQL 加载 `AgentRun` 和 `Installation`，状态改为 RUNNING | `backend/app/tasks/background_agent_task.py` | `_process_issue_with_agent_async()` |
| 11 | 获取最新 Issue、仓库默认分支、语言和 installation token | `backend/app/services/github.py` | `get_issue()`、`get_repository()`、`get_installation_token()` |
| 12 | 创建 Daytona Sandbox 并克隆默认分支 | `backend/app/agents/sandbox/manager.py`、`client.py` | `SandboxManager.acquire()` → `DaytonaClient.create_sandbox()` → `_clone_repository()` |
| 13 | 配置 Git 身份和带 installation token 的 remote | `backend/app/tasks/background_agent_task.py` | `_process_issue_with_agent_async()` 中的 `sandbox.process.exec()` |
| 14 | 注册 Coding Agent 工具 | `backend/app/agents/tools/manager.py` | `get_coder_tools()`、`ToolManager.register_tools()` |
| 15 | 构造 Background Coding Agent | `backend/app/agents/implementation/background_agent.py`、`prompts/coder_prompt.py` | `BackgroundAgent.__init__()`、`build_coder_prompt()` |
| 16 | 启动 Agent Loop | `backend/app/agents/loop.py` | `AgentLoop.execute()` |
| 17 | 每轮调用 LLM 并执行 tool calls | `backend/app/agents/base.py` | `BaseAgent.run()`、`_extract_tool_calls()`、`_add_tool_results_to_messages()` |
| 18 | 调度一个或多个工具 | `backend/app/agents/tools/manager.py` | `ToolManager.execute_batch()` → `execute()` |
| 19 | 读、搜、改、建、删文件 | `backend/app/agents/tools/file_tools.py` | `ReadFileTool`、`SearchFilesTool`、`ReplaceInFilesTool`、`CreateFileTool` 等的 `execute()` |
| 20 | 执行 Shell、代码、测试、Linter | `backend/app/agents/tools/process_tools.py` | `RunCommandTool`、`RunCodeTool`、`RunTestsTool`、`RunLinterTool.execute()` |
| 21 | 建分支、Add、Commit、Push | `backend/app/agents/tools/git_tools.py` | `GitCreateBranchTool`、`GitAddTool`、`GitCommitTool`、`GitPushTool.execute()` |
| 22 | Agent 声明完成 | `backend/app/agents/tools/completion_tools.py` | `FinishTaskTool.execute()` 返回 `completed=True` |
| 23 | Loop 识别完成信号 | `backend/app/agents/base.py` | `_is_complete()`、`_extract_final_result()` |
| 24 | Backend 验证远端分支确实存在 | `backend/app/tasks/background_agent_task.py` | `git ls-remote --heads origin ...` |
| 25 | 收集最后一次 Commit 的变更文件 | `backend/app/tasks/background_agent_task.py` | `git diff --name-only HEAD~1..HEAD` |
| 26 | Backend 创建 Pull Request | `backend/app/services/github.py` | `GitHubService.create_pull_request()` |
| 27 | PostgreSQL 写回 PR URL、编号、Trace 和完成状态 | `backend/app/tasks/background_agent_task.py` | `_process_issue_with_agent_async()`、`db.commit()` |
| 28 | Frontend 每 3 秒轮询结果 | `frontend/src/pages/dashboard/AgentProgressPage.tsx` | `fetchAgentRun()`、`setInterval(..., 3000)` |

### Redis 在链路中的准确位置

```text
process_issue_with_agent.delay(...)
  → Celery 使用 CELERY_BROKER_URL
  → Redis DB 0 保存待消费任务
  → Worker 消费任务
  → Redis DB 1 保存 Celery result backend 数据
```

`AgentRun` 的业务状态和对话不在 Redis，而在 PostgreSQL。当前也没有 Redis Pub/Sub、Stream、分布式锁或 Agent checkpoint。

### 这条链当前最重要的风险

1. **创建记录与投递任务存在竞态**：`launch_agent()` 只 `flush()` 了 `AgentRun`，随后先 `.delay()`，请求依赖 `get_db()` 在 Handler 返回后才 commit。Worker 可能在事务提交前查表，从而把任务当作 `agent_run_not_found` 忽略。
2. **异步函数内部有同步阻塞**：`BaseAgent.run()` 调用同步 `litellm.completion()`；多数 Daytona SDK 调用也是同步的。虽然函数签名是 async，Worker 的事件循环仍会被阻塞。
3. **运行中没有 checkpoint**：iteration、Token、conversation 等主要在 Loop 结束后写库，Worker 崩溃时中间状态会丢失。
4. **没有真正的取消能力**：数据库枚举有 `CANCELED`，但没有 cancel API、Celery revoke、协作式取消检查或 Sandbox 保留策略。
5. **自动重试缺少副作用幂等设计**：`BaseTask` 对所有异常自动重试，但建分支、Push、创建 PR 都是外部副作用，当前没有明确的幂等键或补偿流程。
6. **工具并行不等于真正并行**：`execute_batch()` 使用 `asyncio.gather()`，但工具内部大量调用同步 SDK，同一个事件循环内仍可能串行阻塞。
7. **权限模型仍是 GitHub 专用**：任务直接携带 installation token，尚无企业工单、项目、租户、审批人、环境策略等通用抽象。

## 文件优先级

### 核心文件：后续必须看懂

这些文件构成 Issue → PR 的主链：

- `backend/app/api/agents.py`
- `backend/app/models/agent_run.py`
- `backend/app/core/celery_app.py`
- `backend/app/tasks/background_agent_task.py`
- `backend/app/agents/base.py`
- `backend/app/agents/loop.py`
- `backend/app/agents/prompts/coder_prompt.py`
- `backend/app/agents/tools/manager.py`
- `backend/app/agents/tools/file_tools.py`
- `backend/app/agents/tools/process_tools.py`
- `backend/app/agents/tools/git_tools.py`
- `backend/app/agents/tools/completion_tools.py`
- `backend/app/agents/sandbox/client.py`
- `backend/app/services/github.py`
- `frontend/src/lib/api-client.ts`

### 次要文件：需要时再看

- `backend/app/main.py`：Router 装配很简单，知道入口即可。
- `backend/app/core/config.py`、`db/base.py`、`db/session.py`：改配置或事务边界时再细看。
- `backend/app/agents/sandbox/manager.py`：生命周期薄封装。
- `backend/app/models/installation.py`、`user.py`：做租户、权限和 Connector 时再深入。
- `backend/app/api/issues.py`：GitHub Issue 读取接口。
- `frontend/src/pages/dashboard/IssueDetailPage.tsx`：启动入口。
- `frontend/src/pages/dashboard/AgentProgressPage.tsx`：轮询与 Trace 展示。
- `backend/alembic/`：改数据模型时必须看，但不用第一天逐个读迁移。
- `backend/app/repositories/`：改 CRUD 和事务边界时看。

如果继续保留 PR Review 产品线，再补读：

- `backend/app/services/webhook.py`
- `backend/app/tasks/agent_review_task.py`
- `backend/app/tasks/summary_task.py`
- `backend/app/agents/tools/review_posting_tools.py`
- `backend/app/models/review.py`

### 暂时可以忽略

- `frontend/src/components/ui/`：大多是通用 UI 组件。
- `frontend/src/components/landing/`、Landing Page、品牌图片和动画。
- `static/`。
- `backend/uv.lock`、`frontend/pnpm-lock.yaml`：不要手读，依赖问题时查询即可。
- `backend/.venv/`、`backend/.idea/`、缓存、构建产物。
- `daytona/` submodule 的完整上游源码；先看 Metis 的两层 SDK 适配。
- GCP 部署 Workflow；确定部署平台后再处理。
- Analytics 的图表细节；它不是 Coding Agent Runtime 的主干。

## 二次开发：哪些值得保留

### 建议保留并加强

1. **`AgentRun` 作为运行记录的思想**  
   保留状态、输入快照、资源消耗、对话、结果和错误。后续扩展 checkpoint、审批状态、artifact、parent run、retry attempt 和租户字段。

2. **Celery + Redis 的异步边界**  
   它适合作为第一阶段 Runtime 队列。先补幂等、路由、优先级、取消、限流和状态事件，再决定是否更换任务平台。

3. **`BaseAgent` / `AgentLoop` / `ToolManager` 的最小骨架**  
   结构直观，适合作为后续 Runtime 的起点。重点是把状态持久化、Tool policy、Skill 和 HITL 接入循环，而不是立即推倒重写。

4. **Daytona 隔离执行适配**  
   企业 Coding Agent 必须隔离文件、命令、网络和凭据。应保留 Provider 接口，同时避免 Runtime 与 Daytona SDK 具体类型深度耦合。

5. **文件、进程、测试和 Git 工具分组**  
   工具边界清楚。后续增加权限声明、风险级别、超时、资源预算、审计、输出截断和人工批准即可。

6. **GitHub Service 作为第一个 Connector**  
   不应继续让 GitHub 概念渗透整个 Runtime，但可以保留为 `WorkItemConnector`、`SourceControlConnector` 的第一个实现。

7. **Frontend 的 Issue、AgentRun、Timeline 页面**  
   可以改造成企业工单、运行控制台和 HITL 审批界面。

8. **LangSmith 与结构化运行指标**  
   可继续作为调试手段，但不能代替正式 Evaluation。

## 哪些过重、可选或以后可删除

这里是目标架构建议，不是本次删除清单。

### 如果产品只聚焦“企业工单 → Coding Agent”

可以逐步下线或独立成可选模块：

- PR 自动 Review：`ReviewAgent`、`agent_review_task.py`。
- PR Summary：`SummaryAgent`、`summary_task.py`。
- ReviewComment、Review Analytics 和相关 Dashboard。
- 仓库配置里只服务于 Review 的 sensitivity、ignore patterns 页面。
- Neo-brutalist Landing Page、营销动画和品牌组件。

这些代码不差，只是与“Coding Agent Runtime”主目标不同。应等新主链有回归测试后再删。

### 很可能不需要长期保留

- 根目录 Daytona submodule：如果既不构建也不自托管 Daytona，可删除 gitlink，只保留 SDK 依赖和 Provider 适配。
- 项目特定的 GCP / Cloud Run Workflow：如果企业部署平台不同，应换成独立部署模板。
- `core/redis_client.py`：当前是死代码；但未来做事件流、锁或 checkpoint 前，可以反过来利用它。
- pgAdmin 开发服务：可作为 profile 或单独 compose 文件，而不是所有人默认启动。

## 预期能力的落点建议

### HITL

适合接入：`AgentLoop`、工具执行前、`AgentRun` 状态机和 Frontend Timeline。

建议状态至少增加：

```text
PENDING → RUNNING → WAITING_APPROVAL → RUNNING
                    ├→ REJECTED
                    └→ CANCELED
```

高风险工具如删除文件、执行任意 Shell、Push、创建 PR，应可按项目策略要求审批。

### Skill System

当前 Prompt 和工具列表都是硬编码。可以把 Skill 定义为：

```text
Skill = instructions + allowed_tools + resources + preconditions + output_contract
```

自然落点是 `prompts/`、`ToolManager` 与新的 Skill Registry。不要把 Skill 只做成“更长的 Prompt”。

### Project Memory

当前只有单次 `AgentRun.conversation`，没有跨 Run 记忆。

建议区分：

- 项目事实：构建命令、目录约定、架构决策。
- 运行经验：常见失败、修复方式、测试入口。
- 用户偏好：代码规范、审批要求。
- 检索证据：来源文件、Commit、有效期和可信度。

Memory 应在 Agent 启动前检索，在任务结束后经过筛选再写入，不能直接把完整对话无限累积。

### 多模态 Bug Screenshot

当前 API、Schema 和 LLM message 都以文本为主。需要新增：

- 工单附件和 Screenshot Artifact 模型。
- 受控下载、对象存储和 MIME/大小校验。
- OCR 或 Vision Model 输入适配。
- Screenshot 与代码位置、浏览器日志、复现步骤的关联。

不要把 Base64 图片直接长期塞进 `AgentRun.conversation` JSONB。

### Agent Runtime 异步优化

优先级建议：

1. 先修 `AgentRun commit → enqueue` 竞态，采用可靠事务模式或 Outbox。
2. 把同步 LiteLLM 和 Daytona 调用放入线程池，或切换真正异步 Client。
3. 每轮或每个 Tool 后写 checkpoint/event。
4. 用 SSE/WebSocket 推送事件，Frontend 不再只轮询完整记录。
5. 增加取消令牌、心跳、租约和 Worker 崩溃恢复。
6. 为 Git Push、PR 创建设计幂等键和恢复步骤。
7. 再考虑多队列、并发配额、优先级和不同 Sandbox Provider。

### Benchmark / Evaluation

当前 LangSmith Trace 只是可观测性，不是评测系统；仓库也没有实际测试。

建议建立独立 Eval Harness：

- 固定仓库快照和固定工单。
- 明确通过条件：测试、Lint、Patch 范围、PR 内容、耗时和成本。
- 保存模型、Prompt、Skill、工具版本和 Sandbox 镜像。
- 区分 Agent 成功声明与外部验证成功。
- 支持离线重放和不同模型/策略的 A/B 对比。

## 接手时的建议路线

### 第一阶段：先让现有主链可被信任

- 补 Issue → PR 的集成测试。
- 修事务与 enqueue 竞态。
- 给 Git 副作用增加幂等性。
- 对 Agent 每轮做可恢复持久化。
- 对齐 Backend Schema 与 Frontend TypeScript 类型。

### 第二阶段：把 GitHub 专用流程抽成 Runtime + Connector

- 定义通用 `WorkItem`、`Project`、`Run`、`Artifact`。
- GitHub Issue 变成一个 Connector，而不是 Runtime 的数据模型。
- GitHub PR 变成一个发布目标，而不是 Agent 的唯一完成方式。
- Daytona 变成 Sandbox Provider 的第一个实现。

### 第三阶段：加入企业能力

- HITL、RBAC、审计、Secret scope、网络策略。
- Skill、Project Memory、附件和 Screenshot。
- 队列配额、并发控制、成本预算、失败恢复。
- Benchmark、Evaluation 和发布门禁。

## 建议阅读顺序

下面只列 15 个文件，按 Issue → PR 数据流阅读。不要一开始读完整 Backend README 或所有 UI 组件。

1. `backend/app/api/agents.py`  
   看清一次 Coding Agent 是怎样被创建和投递的，也能立刻发现事务提交边界。

2. `backend/app/models/agent_run.py`  
   这是 Runtime 当前最接近“执行记录”的核心数据模型。

3. `backend/app/core/celery_app.py`  
   理解 Redis、重试、ACK、时限和 Worker 注册方式。

4. `backend/app/tasks/background_agent_task.py`  
   整条 Issue → Sandbox → Agent → Branch → PR 的总编排文件，是最重要的单文件。

5. `backend/app/agents/prompts/coder_prompt.py`  
   当前 Agent 的行为规则、分支策略、测试要求和完成协议都在这里。

6. `backend/app/agents/base.py`  
   理解一次 LLM 调用、Tool Call、消息追加、完成信号和资源上限。

7. `backend/app/agents/loop.py`  
   很短，但它是未来插入 checkpoint、HITL、取消和事件流的关键位置。

8. `backend/app/agents/tools/manager.py`  
   看工具如何注册、转成 LLM Schema 并批量执行，也是 Skill System 的重要扩展点。

9. `backend/app/agents/tools/file_tools.py`  
   理解 Agent 怎样真正读写目标仓库。

10. `backend/app/agents/tools/process_tools.py`  
    理解任意命令、代码、测试和 Linter 的执行边界与风险。

11. `backend/app/agents/tools/git_tools.py`  
    理解分支、Commit 和 Push 怎样成为实际副作用。

12. `backend/app/agents/tools/completion_tools.py`  
    理解 `finish_task()` 如何结束 Agent Loop，以及“Agent 声称完成”与“外部验证完成”的区别。

13. `backend/app/agents/sandbox/client.py`  
    看 Daytona 配置、资源规格、克隆路径和 Sandbox 生命周期起点。

14. `backend/app/services/github.py`  
    看 GitHub App Token、Issue 读取和 PR 创建，后续应把它演化成 Connector。

15. `frontend/src/lib/api-client.ts`  
    从前端视角核对所有 Backend 契约，也能看到 Issue、AgentRun 和轮询相关接口。

读完这 15 个文件，再按需要进入 PR Review、OAuth、Analytics、Repository 管理或具体 UI。
