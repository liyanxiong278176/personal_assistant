<!-- GSD:project-start source:PROJECT.md -->
## Project

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
| **通义千问 (Tongyi Qianwen)** | Qwen 2.0+ | Primary LLM | Best price-performance in 2025, strong Chinese understanding, LangChain integration available |
| **DashScope SDK** | Latest | Alibaba Cloud API client | Official Python SDK for Tongyi Qianwen, stable API access |
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
| **通义千问 VL** | Image recognition | Multi-modal model for photo identification |
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
| **LLM** | Tongyi Qianwen | GPT-4, Claude | Chinese LLMs required for project constraints, more cost-effective |
| **Deployment** | Docker + Nginx | Serverless (Vercel/FC) | Python backend needs long-running processes for WebSocket/streaming |
## What NOT to Use
| Anti-Pattern | Why Avoid | What to Use Instead |
|--------------|-----------|---------------------|
| **LangChain v1.0** | Migration issues reported, unstable for production | LangChain 0.3.x |
| **Flask for streaming** | No native async support, requires additional setup | FastAPI with built-in WebSocket support |
| **Pinecone from day 1** | Cost scales quickly, overkill for MVP | ChromaDB local persistent storage |
| **Direct API calls without SDK** | Reinventing streaming, error handling | Vercel AI SDK or DashScope SDK |
| **Redux for chat state** | Overcomplicated for chat history | Vercel AI SDK's built-in state management |
| **PostgreSQL for vectors** | Additional infrastructure complexity | ChromaDB with SQLite backend |
| **OpenAI/ChatGPT API** | Access issues in China, higher cost | Tongyi Qianwen or other Chinese LLMs |
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
- [国产AI全面崛起：通义千问、Kimi、GLM、文心深度对比](https://juejin.cn/post/7615267467041194026) - Tongyi Qianwen ranking and capabilities
- [LangChain Agents in 2025 Tutorial](https://www.youtube.com/watch?v=Gi7nqB37WEY) - v0.3 specific guidance
### LOW Confidence (Requires Verification)
- Specific DashScope Python SDK version (website 404'd, verify directly with Alibaba Cloud docs)
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
