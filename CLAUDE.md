<!-- GSD:project-start source:PROJECT.md -->
## Project
执行完成总结                                                               
                                                                                                                                                                                                                                                    
  ✅ Agent Core 实现计划已完成！                                                                                                                                                                                                       ─             
                                                                                                                                                                                                                                                    
  已完成的 Phase                                                                                                                                                                                                                                    
                                                                                                                                                                                                                                                    
  ┌────────────┬───────────────────────┬──────┐                                                                                                                                                                                                 
  │   Phase    │      任务     │ 状态 │                                                                                                                                                                                                     
  ├────────────┼───────────────────────┼──────┤                                                                                                                                                                                                     
  │ Phase 0    │ LLM 客户端封装        │ ✅   │                                                                                                                                                                                                      
  ├────────────┼───────────────────────┼──────┤                                                                                                                                                                                                     
  │ Phase 1.1  │ Core 包结构和错误定义 │ ✅   │                                                                                                                                                                                                      
  ├────────────┼───────────────────────┼──────┤                                                                                                                                                                                                     
  │ Phase 1.2  │ 工具基类和注册表      │ ✅   │                                                                                                                                                                                                      
  ├────────────┼───────────────────────┼──────┤                                                                                                                                                                                                     
  │ Phase 1.2b │ 工具执行器            │ ✅   │                                                                                                                                                                                                      
  ├────────────┼───────────────────────┼──────┤                                                                                                                                                                                                     
  │ Phase 1.3  │ 提示词构建器          │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 1.4  │ QueryEngine 总控      │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 2.1  │ Slash 命令系统        │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 2.2  │ 意图路由集成测试      │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 2.3  │ Skill 触发系统        │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 3.1  │ 记忆层级管理          │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 3.2  │ 自动记忆注入          │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 3.3  │ 记忆晋升机制          │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 4.1  │ Token 估算器          │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 4.2  │ 上下文压缩器和管理器  │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Phase 5.1  │ Coordinator 和 Worker │ ✅   │
  ├────────────┼───────────────────────┼──────┤
  │ Final      │ 包导出和文档          │ ✅   │
  └────────────┴───────────────────────┴──────┘

  创建的文件结构

  backend/app/core/
  ├── __init__.py                    # 包导出（完整）
  ├── README.md                      # 使用指南
  ├── query_engine.py                # 总控中心
  ├── errors.py                      # 错误定义
  ├── llm/
  ��   ├── __init__.py
  │   └── client.py                  # LLM 客户端
  ├── tools/
  │   ├── __init__.py
  │   ├── base.py                    # 工具基类
  │   ├── registry.py                # 工具注册表
  │   └── executor.py                # 工具执行器
  ├── prompts/
  │   ├── __init__.py
  │   ├── layers.py                  # 提示词层级
  │   └── builder.py                 # 提示词构建器
  ├── intent/
  │   ├── __init__.py
  │   ├── commands.py                # Slash 命令
  │   └── skills.py                  # Skill 触发
  ├── context/
  │   ├── __init__.py
  │   ├── tokenizer.py               # Token 估算
  │   ├── compressor.py              # 上下文压缩
  │   └── manager.py                 # 上下文管理
  ├── memory/
  │   ├── __init__.py
  │   ├── hierarchy.py               # 记忆层级
  │   ├── injection.py               # 记忆注入
  │   └── promoter.py                # 记忆晋升
  └── coordinator/
      ├── __init__.py
      ├── worker.py                  # Worker 执行器
      └── coordinator.py             # 协调器

  tests/core/
  ├── test_llm.py
  ├── test_tools.py
  ├── test_prompts.py
  ├── test_intent.py
  ├── test_memory.py
  ├── test_context.py
  ├── test_coordinator.py
  └── integration/
      └── test_query_engine.py

  下一步

  Agent Core 现在已完全实现。你可以：

  1. 运行完整测试套件：cd backend && pytest tests/core/ -v
  2. 开始集成具体工具（天气 API、地图 API 等）
  3. 连接前端：通过 FastAPI 端点暴露 QueryEngine
  4. 部署测试：验证各组件在实际场景中的表现


**AI旅游助手 (Travel Assistant)**

一款面向个人旅行者的AI智能旅游助手，通过对话式交互帮助用户规划行程、推荐景点、查询信息。同时作为校招AI应用开发岗位的面试展示项目，全面展示Agent工具调用、多模态理解、上下文记忆管理等AI应用开发能力。

**Core Value:** **智能规划 + 个性化推荐**：Agent自动调用多源API为用户生成最优旅行方案，并记住用户偏好持续优化推荐。

### Constraints

- **时间线**：渐进式开发，按需逐步完善
- **技术栈**：React前端 + FastAPI后端 + 国产大模型API
- **数据来源**：真实API（高德/百度地图、天气API等）
- **部署方式**：云服务器部署（阿里云/腾讯云学生服务器）
- **成本**：考虑API调用成本，合理使用免费额度
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### Frontend Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **React** | 19.x | Core UI framework | Latest stable with improved concurrent rendering and Server Components support |
| **Next.js** | 15.x | Full-stack React framework | Built-in API routes, server components, excellent deployment options |
| **shadcn/ui** | Latest | Component library | Copy-paste components you own, works with Tailwind v4, highly customizable |
| **Tailwind CSS** | v4.x | Styling | Latest version with improved performance and CSS-first configuration |
| **Vercel AI SDK** | 6.x (Latest) | AI streaming hooks | `useChat` hook for streaming responses, unified provider API, multi-model support |
### Backend Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **FastAPI** | 0.115+ | Python web framework | High performance (10k+ concurrent connections), native async/await, WebSocket support for streaming |
| **Uvicorn** | Latest | ASGI server | Production-ready server with uvloop for high performance |
| **Pydantic** | v2.x | Data validation | Type-safe data validation, integrated with FastAPI |
| **python-multipart** | Latest | Form data parsing | Required for file uploads (image recognition) |
### AI Model Integration (Chinese LLMs)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **DeepSeek** | deepseek-chat | Primary LLM | Best price-performance in 2025, strong Chinese understanding, OpenAI-compatible API |
| **OpenAI SDK** | Latest | API client | Official Python SDK, compatible with DeepSeek API |
| **LangChain** | 0.3.x | Agent framework | Comprehensive tool calling support, extensive Chinese model integrations |
- **文心一言 (Ernie Bot)** - Good Chinese context, slightly higher cost
- **智谱GLM** - Strong agent capabilities, good for automation tasks
- **Kimi** - Excellent for long text processing (documents, reports)
### Agent Framework
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **LangChain** | 0.3.x (NOT v1.0) | Agent orchestration | Stable version with proven tool calling, v1.0 has migration issues (based on community reports) |
| **LangChain Community** | Latest | Third-party integrations | Access to extended provider ecosystem |
### Vector Database (for RAG)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **ChromaDB** | Latest | Local vector storage | Easiest setup for local development, persistent storage with PersistentClient, LangChain integration |
| **SQLite** | (bundled) | Chroma backend | Zero-config persistent storage |
- **Qdrant** - Best overall for self-hosting at scale, written in Rust for performance
- **Pinecone** - Easiest managed service, use until you have real usage data
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **httpx** | Latest | Async HTTP client | For making API calls to external services (weather, maps) |
| **python-dotenv** | Latest | Environment variables | Managing API keys and configuration |
| **aiofiles** | Latest | Async file operations | For handling image uploads asynchronously |
| **websockets** | Latest | WebSocket support | For real-time streaming responses (optional, FastAPI has built-in support) |
### External APIs
| Service | Purpose | Why |
|---------|---------|-----|
| **高德地图 API** | Maps, geocoding, POI search | Comprehensive Chinese location data, free tier available |
| **和风天气 API** | Weather data | Reliable Chinese weather data, free tier for developers |
| **DeepSeek VL** | Image recognition | Multi-modal model for photo identification |
## Deployment
### Development Environment
# Frontend
# Backend
### Production Deployment (Alibaba Cloud ECS)
## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| **Frontend Framework** | Next.js + React | Vite + React | Next.js provides API routes for simpler architecture |
| **UI Components** | shadcn/ui | Chakra UI, MUI | shadcn gives you code ownership, better customization |
| **Backend** | FastAPI | Flask, Django | FastAPI has native async, better for AI streaming |
| **AI SDK** | Vercel AI SDK | Direct API calls | Vercel SDK handles streaming complexity automatically |
| **Vector DB** | ChromaDB (local) | Pinecone (cloud) | Start local, migrate when needed. Pinecone costs add up |
| **Agent Framework** | LangChain 0.3.x | LlamaIndex, LangGraph | LangChain has best Chinese model integration. LangGraph is newer, less proven |
| **LLM** | DeepSeek | GPT-4, Claude | Chinese LLMs required for project constraints, more cost-effective |
| **Deployment** | Docker + Nginx | Serverless (Vercel/FC) | Python backend needs long-running processes for WebSocket/streaming |
## What NOT to Use
| Anti-Pattern | Why Avoid | What to Use Instead |
|--------------|-----------|---------------------|
| **LangChain v1.0** | Migration issues reported, unstable for production | LangChain 0.3.x |
| **Flask for streaming** | No native async support, requires additional setup | FastAPI with built-in WebSocket support |
| **Pinecone from day 1** | Cost scales quickly, overkill for MVP | ChromaDB local persistent storage |
| **Direct API calls without SDK** | Reinventing streaming, error handling | Vercel AI SDK or OpenAI SDK |
| **Redux for chat state** | Overcomplicated for chat history | Vercel AI SDK's built-in state management |
| **PostgreSQL for vectors** | Additional infrastructure complexity | ChromaDB with SQLite backend |
| **OpenAI/ChatGPT API** | Access issues in China, higher cost | DeepSeek or other Chinese LLMs |
## Architecture Overview
## Installation Commands
### Frontend
# Create Next.js app with TypeScript
# Install dependencies
# Initialize shadcn/ui
### Backend
# Create Python virtual environment
# Install FastAPI with standard dependencies
# Install AI/Agent dependencies
# Install supporting libraries
## Sources
### HIGH Confidence (Official Documentation)
- [FastAPI Official Documentation](https://fastapi.tiangolo.com/) - Verified 2026-03-30
- [Vercel AI SDK Documentation v6](https://sdk.vercel.ai/docs) - Verified 2026-03-30
- [shadcn/ui Official Site](https://ui.shadcn.com/) - Verified 2026-03-30
- [LangChain Providers Integration](https://python.langchain.com/docs/integrations/providers/) - Verified 2026-03-30
- [Qdrant Documentation](https://qdrant.tech/documentation/) - Verified 2026-03-30
### MEDIUM Confidence (Web Search Verified)
- [Vector Database Comparison 2025](https://medium.com/tech-ai-made-easy/vector-database-comparison-pinecone-vs-weaviate-vs-qdrant-vs-faiss-vs-milvus-vs-chroma-2025-15bf152f891d) - Qdrant recommended as overall best
- [国产AI全面崛起：DeepSeek、Kimi、GLM、文心深度对比](https://juejin.cn/post/7615267467041194026) - Chinese LLM comparison
- [LangChain Agents in 2025 Tutorial](https://www.youtube.com/watch?v=Gi7nqB37WEY) - v0.3 specific guidance
### LOW Confidence (Requires Verification)
- Exact pricing for Chinese LLM APIs (changes frequently, verify with each provider)
- Exact pricing for Chinese LLM APIs (changes frequently, verify with each provider)
## Notes
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
