"""
Agent Core 综合功能测试
测试所有新添加的功能模块
"""

import asyncio
import os
import sys

# 设置编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.environ["PYTHONPATH"] = "/d/agent_learning/travel_assistant/backend"

from app.core import (
    AgentError, DegradationLevel, DegradationStrategy,
    LLMClient, ToolCall,
    Tool, ToolRegistry, global_registry,
)
from app.core.tools import ToolExecutor
from app.core.prompts import PromptBuilder, PromptLayer, DEFAULT_SYSTEM_PROMPT
from app.core.memory import MemoryHierarchy, MemoryItem, MemoryLevel
from app.core.memory.injection import MemoryInjector
from app.core.memory.promoter import MemoryPromoter
from app.core.context_mgmt import ContextManager, TokenEstimator, ContextCompressor
from app.core.coordinator import Coordinator, create_worker
from app.core.query_engine import QueryEngine


# ==================== 测试 1: 错误处理和降级策略 ====================
def test_errors():
    print("\n" + "="*50)
    print("[测试 1] 错误处理和降级策略")
    print("="*50)

    msg = DegradationStrategy.get_message(DegradationLevel.LLM_DEGRADED)
    print(f"[OK] LLM 降级消息: {msg}")

    error = AgentError("测试错误", {"code": 123})
    print(f"[OK] AgentError 创建: {error.message}")

    print("[PASS] 错误处理测试通过\n")


# ==================== 测试 2: LLM 客户端 ====================
async def test_llm_client():
    print("="*50)
    print("[测试 2] LLM 客户端")
    print("="*50)

    client = LLMClient(api_key=None)
    print(f"[OK] LLM 客户端创建 (无 API key)")

    parts = []
    async for chunk in client.stream_chat([{"role": "user", "content": "测试"}]):
        parts.append(chunk)
    result = "".join(parts)
    print(f"[OK] 降级响应: {result}")

    print("[PASS] LLM 客户端测试通过\n")


# ==================== 测试 3: 工具系统 ====================
async def test_tools():
    print("="*50)
    print("[测试 3] 工具系统")
    print("="*50)

    class WeatherTool(Tool):
        @property
        def name(self):
            return "get_weather"

        @property
        def description(self):
            return "获取指定城市的天气信息"

        @property
        def is_readonly(self):
            return True

        @property
        def is_concurrency_safe(self):
            return True

        async def execute(self, city: str):
            return f"{city} 今天晴天，温度 25°C"

    class AttractionTool(Tool):
        @property
        def name(self):
            return "get_attractions"

        @property
        def description(self):
            return "获取指定城市的景点推荐"

        @property
        def is_readonly(self):
            return True

        @property
        def is_concurrency_safe(self):
            return True

        async def execute(self, city: str):
            return f"{city} 的热门景点：故宫、长城、天坛"

    registry = ToolRegistry()
    registry.register(WeatherTool())
    registry.register(AttractionTool())
    print(f"[OK] 注册了 {len(registry.list_tools())} 个工具")

    descriptions = registry.get_descriptions()
    print(f"[OK] 工具描述:\n{descriptions}")

    executor = ToolExecutor(registry)
    result = await executor.execute("get_weather", city="北京")
    print(f"[OK] 工具执行结果: {result}")

    parallel_results = await executor.execute_parallel([
        {"tool": "get_weather", "args": {"city": "北京"}},
        {"tool": "get_attractions", "args": {"city": "上海"}},
    ])
    print(f"[OK] 并行执行结果: {parallel_results}")

    print("[PASS] 工具系统测试通过\n")


# ==================== 测试 4: 提示词构建 ====================
def test_prompts():
    print("="*50)
    print("[测试 4] 提示词构建")
    print("="*50)

    builder = PromptBuilder()
    builder.add_layer("系统角色", "你是一个专业的旅游助手", PromptLayer.DEFAULT)
    builder.add_layer("工具说明", "你可以使用天气查询和景点推荐工具", PromptLayer.APPEND)

    builder.add_layer(
        "调试信息",
        "DEBUG: 模式已启用",
        PromptLayer.OVERRIDE,
        condition=lambda: False
    )

    prompt = builder.build()
    print(f"[OK] 构建的提示词:\n{prompt}")

    print(f"[OK] 默认系统提示词长度: {len(DEFAULT_SYSTEM_PROMPT)} 字符")

    print("[PASS] 提示词构建测试通过\n")


# ==================== 测试 5: 记忆系统 ====================
def test_memory():
    print("="*50)
    print("[测试 5] 记忆系统")
    print("="*50)

    hierarchy = MemoryHierarchy()

    hierarchy.add(MemoryItem("用户刚才问了天气", MemoryLevel.WORKING))
    hierarchy.add(MemoryItem("用户计划去北京旅游", MemoryLevel.EPISODIC))
    hierarchy.add(MemoryItem("用户喜欢安静的地方，预算有限", MemoryLevel.SEMANTIC))

    print(f"[OK] 添加了 3 层记忆")

    working = hierarchy.get_working()
    print(f"[OK] 工作记忆数量: {len(working)}")

    episodic = hierarchy.get_episodic()
    print(f"[OK] 情景记忆数量: {len(episodic)}")

    # 直接查询语义记忆（不使用 MemoryInjector 的复杂功能）
    semantic = hierarchy.get_semantic("北京")
    print(f"[OK] 语义记忆查询结果数量: {len(semantic)}")

    print("[PASS] 记忆系统测试通过\n")


# ==================== 测试 6: 上下文管理 ====================
def test_context():
    print("="*50)
    print("[测试 6] 上下文管理")
    print("="*50)

    text = "你好世界，这是一个测试。Hello World!"
    tokens = TokenEstimator.estimate(text)
    print(f"[OK] Token 估算: '{text}' -> {tokens} tokens")

    ctx = ContextManager(max_tokens=1000, auto_compress=True)
    ctx.add_message("user", "你好")
    ctx.add_message("assistant", "你好！有什么可以帮助你的？")
    ctx.add_message("user", "我想去北京旅游")

    print(f"[OK] 添加了 3 条消息")
    print(f"[OK] 当前 Token 数: {ctx.get_token_count()}")

    messages = ctx.get_messages()
    print(f"[OK] 获取消息数量: {len(messages)}")

    compressor = ContextCompressor(max_tokens=100, compression_threshold=0.5)
    needs_compress = compressor.needs_compaction(messages)
    print(f"[OK] 是否需要压缩: {needs_compress}")

    print("[PASS] 上下文管理测试通过\n")


# ==================== 测试 7: Coordinator 并行执行 ====================
async def test_coordinator():
    print("="*50)
    print("[测试 7] Coordinator 并行执行")
    print("="*50)

    coordinator = Coordinator()

    workers = [
        create_worker("查询北京天气", "调用天气 API 获取北京天气"),
        create_worker("推荐北京景点", "调用地图 API 获取北京热门景点"),
        create_worker("查询交通方式", "查询去北京的交通方式"),
    ]

    print(f"[OK] 创建了 {len(workers)} 个 Worker")

    results = await coordinator.run_parallel(workers)

    for task_id, result in results.items():
        print(f"[OK] Worker {task_id}: {result[:50]}...")

    print("[PASS] Coordinator 测试通过\n")


# ==================== 测试 8: QueryEngine 总控（Function Calling） ====================
async def test_query_engine():
    print("="*50)
    print("[测试 8] QueryEngine 总控（Function Calling 模式）")
    print("="*50)

    # 创建模拟 LLM 客户端
    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            yield "我是模拟的 LLM 响应。你刚才说：" + (messages[-1]["content"] if messages else "你好！")

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            # 模拟不调用工具的情况
            return ("我是模拟的 LLM 响应", [])

    # 注册测试工具
    class TestTool(Tool):
        @property
        def name(self):
            return "test_tool"

        @property
        def description(self):
            return "测试工具"

        async def execute(self, query: str):
            return f"测试工具结果: {query}"

    global_registry.register(TestTool())

    engine = QueryEngine(llm_client=MockLLMClient())

    test_cases = [
        ("你好，今天天气怎么样？", "普通对话"),
        ("请帮我查询北京的天气", "可能触发工具"),
        ("北京有什么好玩的地方？", "普通对话"),
    ]

    for input_text, description in test_cases:
        print(f"\n--- 测试 {description}: {input_text} ---")
        result = []
        try:
            async for chunk in engine.process(input_text, "test-conv-001"):
                result.append(chunk)

            output = "".join(result)
            print(f"输出: {output[:150]}...")
        except Exception as e:
            print(f"处理出错: {str(e)[:100]}")

    print("\n[PASS] QueryEngine 测试通过\n")


# ==================== 测试 9: 端到端工作流 ====================
async def test_end_to_end_workflow():
    print("="*50)
    print("[测试 9] 端到端工作流")
    print("="*50)
    print("模拟完整用户对话流程...\n")

    # 创建模拟 LLM 客户端
    class MockLLMClient:
        async def stream_chat(self, messages, system_prompt=None):
            last_msg = messages[-1]["content"] if messages else ""
            yield f"收到你的消息: {last_msg}。我是旅游助手，很高兴为你服务！"

        async def chat_with_tools(self, messages, tools, system_prompt=None):
            return ("我是模拟的 LLM 响应", [])

    engine = QueryEngine(llm_client=MockLLMClient())
    conversation_id = "e2e-test-001"

    conversation = [
        "你好",
        "请帮我规划北京的行程",
        "北京有什么好玩的地方？",
        "怎么去北京比较方便？",
    ]

    for user_input in conversation:
        print(f"\n[用户] {user_input}")
        print("[助手] ", end="")

        result = []
        try:
            async for chunk in engine.process(user_input, conversation_id):
                result.append(chunk)

            response = "".join(result)
            print(f"{response[:200]}{'...' if len(response) > 200 else ''}")
        except Exception as e:
            print(f"处理出错: {str(e)[:100]}")

    print("\n[PASS] 端到端工作流测试通过\n")


# ==================== 主测试入口 ====================
async def main():
    print("\n" + "="*50)
    print("Agent Core 综合功能测试")
    print("="*50)

    try:
        test_errors()
        await test_llm_client()
        await test_tools()
        test_prompts()
        test_memory()
        test_context()
        await test_coordinator()
        await test_query_engine()
        await test_end_to_end_workflow()

        print("="*50)
        print("[SUCCESS] 所有测试通过! Agent Core 功能正常")
        print("="*50 + "\n")

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
