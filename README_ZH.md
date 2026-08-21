<p align="center">
  <img src="static/metis-logo.svg" alt="Metis logo" width="520" />
</p>
<p align="center">AI 驱动的 GitHub Code Review 平台</p>

<p align="center">
  <a href="https://github.com/KacemMathlouthi/metis">
    <img src="https://img.shields.io/badge/METIS-SEE%20MORE%20DETAILS-FF9F1C?style=for-the-badge&labelColor=111111&logo=github&logoColor=FFFFFF" alt="Metis See More Details" />
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB" alt="React 19" />
  <img src="https://img.shields.io/badge/Celery-37814A?style=for-the-badge&logo=celery&logoColor=white" alt="Celery" />
  <img src="https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis" />
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
  <img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Daytona-Sandbox-111111?style=for-the-badge&logo=docker&logoColor=white" alt="Daytona Sandbox" />
  <img src="https://img.shields.io/badge/Kubernetes-326CE5?style=for-the-badge&labelColor=111111&logo=kubernetes&logoColor=white" alt="Kubernetes" />
</p>

<p align="center">
  <img src="frontend/src/assets/Handshake-with-AI.png" alt="Human and AI handshake" width="100%" />
</p>

## 项目概述

Metis 是一个以 GitHub App 形式构建、由 AI 驱动的 GitHub Code Reviewer。它监听 Pull Request webhook，在隔离的 Sandbox 中分析变更，并将可操作的问题直接发布到 PR 上。

**生产级 Monorepo**：
- **Backend**：Python、FastAPI、Celery、PostgreSQL、Redis、AI Agent
- **Frontend**：React 19、TypeScript、Vite（Rolldown）、Tailwind v4、Neo-brutalist UI
- **Agent Runtime**：Daytona Sandbox + 工具增强型 LLM Agent
- **多 LLM 支持**：LiteLLM（Vertex AI、OpenAI、Anthropic、Mistral）

## 核心能力

### AI 驱动的 Code Review
- **自主 Agent** 在隔离的 Sandbox 中分析 PR
- **渐进式行内问题** 直接发布到 Diff 对应行
- **多 LLM Provider 支持**——只需更改一个环境变量即可切换 Provider
- **可配置的敏感度**——支持从 INFO 到 CRITICAL 的问题级别
- **分类标签**——SECURITY、PERFORMANCE、BUG、STYLE 等

### Issue 到 PR 工作流
- 从 GitHub Issue 启动**自主 Coding Agent**
- Agent 编写代码、运行测试、Commit 并创建 PR
- 通过指标和时间线实时跟踪进度
- 完整持久化对话和 Tool Trace

### Repository 管理
- **多 Repository 支持**——一个 GitHub App 管理多个 Repo
- **按 Repository 配置**——自定义指令和忽略模式
- **GitHub OAuth 集成**——安全的用户身份认证

### Analytics Dashboard
- Review 指标和趋势
- 带筛选功能的 AI 检测问题表格
- Agent 运行历史和性能指标
- 实时进度监控

## 目录

- [架构](#架构)
- [Repository 结构](#repository-结构)
- [快速开始](#快速开始)
- [文档](#文档)
- [开发](#开发)
- [测试与质量](#测试与质量)
- [部署](#部署)
- [安全](#安全)
- [参与贡献](#参与贡献)
- [许可证](#许可证)

## 架构

### 高层系统设计

```
┌─────────────┐
│   GitHub    │
│   Webhooks  │
└──────┬──────┘
       │ Pull Request Event
       ▼
┌───────────────────────────────────┐
│       FastAPI Backend             │
│  ┌─────────────────────────────┐  │
│  │   Webhook Handler           │  │
│  │   - Verify signature        │  │
│  │   - Create Review (PENDING) │  │
│  │   - Queue Celery tasks      │  │
│  │   - Return 202 Accepted     │  │
│  └─────────────┬───────────────┘  │
│                │                  │
└────────────────┼──────────────────┘
                 │
                 ▼
         ┌───────────────┐
         │  Redis Queue  │
         └───────┬───────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│       Celery Worker                 │
│  ┌───────────────────────────────┐  │
│  │   AI Agent System             │  │
│  │                               │  │
│  │  1. Create Daytona Sandbox    │  │
│  │  2. Clone PR Branch           │  │
│  │  3. Run Agent Loop:           │  │
│  │     - Plan (LLM)              │  │
│  │     - Execute Tools           │  │
│  │     - Post Findings           │  │
│  │     - Evaluate                │  │
│  │  4. Post Final Review         │  │
│  │  5. Cleanup Sandbox           │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 核心请求流程

1. **GitHub 发送 webhook**，通知 PR 变更（opened、synchronize、reopened）
2. **Backend 校验签名**并记录待处理 Review
3. **Celery 将 Agent Task 加入队列**，用于 Review 和 Summary 生成
4. **Agent 在 Sandbox 中执行**，并拥有受控的工具访问权限：
   - 读取文件并分析代码
   - 运行测试和 Linter
   - 渐进式发布行内问题
   - 生成最终 Review Summary
5. **问题发布到 GitHub**，作为 Review Comment，并持久化到数据库
6. **Frontend Dashboard** 展示进度、Analytics 和 Repository 控制项

### Agent 工具

**可用工具（共 23 个）**：
- 文件操作（6）：读取、列出、搜索、替换、创建、删除
- Git 操作（8）：状态、分支、创建分支、Checkout、Add、Commit、Push、Pull
- 进程执行（4）：命令、代码、测试、Linter
- Review 发布（2）：`post_inline_finding`、`post_file_finding`
- 完成工具（3）：`finish_review`、`finish_task`、`finish_summary`

### 多 LLM 支持

通过一个环境变量切换 AI Provider：

```bash
# Vertex AI (Google)
MODEL_NAME=vertex_ai/gemini-3-flash-preview

# OpenAI
MODEL_NAME=gpt-4o

# Anthropic
MODEL_NAME=claude-3-5-sonnet-20241022

# Mistral
MODEL_NAME=mistral/mistral-large-latest
```

无需修改代码。LiteLLM 会处理不同 Provider 之间的差异。

## Repository 结构

```
metis/
├── backend/                    # FastAPI backend (Python)
│   ├── app/
│   │   ├── api/                # API route handlers
│   │   ├── core/               # Configuration & infrastructure
│   │   ├── db/                 # Database layer
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── repositories/       # Repository pattern (data access)
│   │   ├── services/           # Business logic
│   │   ├── agents/             # AI Agent System
│   │   │   ├── base.py         # BaseAgent
│   │   │   ├── loop.py         # AgentLoop orchestrator
│   │   │   ├── implementation/ # ReviewAgent, BackgroundAgent, SummaryAgent
│   │   │   ├── prompts/        # System prompts
│   │   │   ├── sandbox/        # Daytona integration
│   │   │   └── tools/          # 23 tools
│   │   ├── schemas/            # Pydantic models
│   │   ├── tasks/              # Celery background tasks
│   │   └── utils/              # Utilities
│   ├── alembic/                # Database migrations
│   ├── tests/                  # Test suite
│   └── README.md               # Backend documentation
│
├── frontend/                   # React frontend (TypeScript)
│   ├── src/
│   │   ├── components/         # React components
│   │   │   ├── ui/             # shadcn/ui components
│   │   │   ├── dashboard/      # Dashboard components
│   │   │   ├── landing/        # Landing page sections
│   │   │   └── issues/         # Issue & agent components
│   │   ├── contexts/           # React Context providers
│   │   ├── pages/              # Route pages
│   │   ├── lib/                # Utilities (API client, icons)
│   │   └── types/              # TypeScript definitions
│   └── README.md               # Frontend documentation
│
├── static/                     # Static assets
│   └── metis-logo.svg
│
├── docker-compose.dev.yml      # Development infrastructure
├── CONTRIBUTING.md             # Contribution guidelines
├── CODE_OF_CONDUCT.md          # Code of conduct
├── SECURITY.md                 # Security policy
└── README.md                   # This file
```

## 快速开始

### 前置条件

- **Python 3.10+**
- **Node.js 20+**，并安装 pnpm
- **Docker 和 Docker Compose**
- **GitHub App** 凭据
- **Daytona 账户** (https://app.daytona.io)
- **UV** 包管理器

### 1. 启动基础设施

```bash
# Start PostgreSQL, Redis, pgAdmin, Redis Insight
docker-compose -f docker-compose.dev.yml up -d
```

**服务**：
- PostgreSQL：`localhost:5432`
- Redis：`localhost:6379`
- pgAdmin：`http://localhost:5050` (admin@example.com / admin)

### 2. 配置 Backend

```bash
cd backend

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your credentials

# Run migrations
alembic upgrade head

# Start backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3）运行 Worker
```bash
# Start Celery worker
cd backend
celery -A app.core.celery_app worker --loglevel=info
```

**可选——Celery 监控**：

```bash
# Start Flower
celery -A app.core.celery_app flower --port=5555
# Visit http://localhost:5555
```

Backend 地址：`http://localhost:8000`

### 4. 配置 Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Start dev server
pnpm dev
```

Frontend 地址：`http://localhost:5173`

### 5. 配置 GitHub App

**快速概要**：
1. 创建具有所需权限的 GitHub App
2. 生成并下载私钥（`.pem` 文件）
3. 将 webhook URL 设置为 `http://your-domain/webhooks/github`
4. 将凭据添加到 Backend 的 `.env`

### 6. 访问应用

1. **访问 Frontend**：`http://localhost:5173`
2. **点击 “Login with GitHub”**——重定向到 GitHub OAuth
3. **授权应用**——重定向回 Dashboard
4. **同步 Repository**——在 Repositories 页面点击 “Sync from GitHub”
5. **启用 Review**——打开希望 Metis Review 的 Repository 开关
6. 在已启用的 Repository 中**创建 PR**——Metis 会自动进行 Review！

## 文档

### 核心文档

- **[Backend README](backend/README.md)**——完整的 Backend 架构、API 参考和 Agent System 说明
- **[Frontend README](frontend/README.md)**——React App 结构、组件和状态管理

## 开发

### 开发工作流

**Backend**：
```bash
cd backend

# Code quality
ruff check .              # Lint
ruff format .             # Format
mypy app/                 # Type check
pytest                    # Run tests

# Database
alembic revision --autogenerate -m "description"
alembic upgrade head

# Pre-commit hooks
pre-commit install
pre-commit run --all-files
```

**Frontend**：
```bash
cd frontend

# Code quality
pnpm lint                 # ESLint
pnpm format               # Prettier
pnpm build                # Type check + build

# Development
pnpm dev                  # Dev server with HMR
```

### 开发技术栈

**Backend**：
- FastAPI：异步 API Endpoint
- Celery：后台任务处理
- SQLAlchemy 2.0：异步 ORM
- Alembic：数据库迁移
- Redis：任务队列和缓存
- LiteLLM：访问多个 LLM Provider
- Daytona：隔离代码执行

**Frontend**：
- React 19 和 React Compiler
- TypeScript：类型安全
- Vite（Rolldown）：快速构建
- Tailwind CSS v4：样式
- shadcn/ui：组件库
- React Router v7：路由

### 持续集成

**GitHub Actions Workflow**：
- Backend：Ruff、MyPy、Pytest（Push 时运行）
- Frontend：ESLint、TypeScript、Build（Push 时运行）
- CodeQL：安全扫描

### 环境变量

**Backend**（`.env`）：
```bash
# Database
DATABASE_URL=postgresql+asyncpg://...

# GitHub
GITHUB_APP_ID=...
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_WEBHOOK_SECRET=...
GITHUB_SECRET_KEY_PATH=./app.private-key.pem

# LLM Provider
MODEL_NAME=vertex_ai/gemini-3-flash-preview
VERTEX_PROJECT=...
VERTEX_LOCATION=global

# Daytona
DAYTONA_API_KEY=...
DAYTONA_TARGET=eu
```

**Frontend**（`.env.production`）：
```bash
VITE_API_URL=https://api.metis.example.com
```


## 安全
- 强制校验 GitHub Event 的 Webhook 签名。
- OAuth Token 加密存储。
- Session Auth 使用 HTTP-only Cookie 和刷新流程。

如果你发现安全漏洞，请提交私密安全报告，或在 `SECURITY.md` 完善前直接联系维护者。

## 参与贡献

欢迎贡献！请先阅读我们的贡献指南。

### 如何贡献

1. **Fork Repository**
2. **创建 Feature Branch**：`git checkout -b feature/amazing-feature`
3. 按照我们的代码标准**进行修改**
4. **运行质量检查**：
   - Backend：`ruff check . && mypy app/ && pytest`
   - Frontend：`pnpm lint && pnpm format:check && pnpm build`
5. **提交修改**：`git commit -m 'feat: add amazing feature'`
6. **Push 到 Branch**：`git push origin feature/amazing-feature`
7. **创建 Pull Request**


<p align="center">
  <img src="frontend/src/assets/lechat.gif" alt="LeChat" width="360" />
</p>

## 许可证

本项目采用 MIT License——详情请参阅 [LICENSE](LICENSE) 文件。

## Star 历史

如果你觉得 Metis 有用，请考虑为 Repository 点 Star！

<a href="https://star-history.com/#KacemMathlouthi/metis&Date">
  <picture>
	    <source
	      media="(prefers-color-scheme: dark)"
	      srcset="https://api.star-history.com/svg?repos=KacemMathlouthi/metis&type=Date&theme=dark&legend=bottom-right&cache=2026-02-15"
	    />
	    <source
	      media="(prefers-color-scheme: light)"
	      srcset="https://api.star-history.com/svg?repos=KacemMathlouthi/metis&type=Date&legend=bottom-right&cache=2026-02-15"
	    />
    <img
      alt="Star History Chart"
      src="https://api.star-history.com/svg?repos=KacemMathlouthi/metis&type=Date&legend=bottom-right&cache=2026-02-15"
    />
  </picture>
</a>

---

<p align="center">用 ❤️ 打造，只为更好的 Code Review</p>
