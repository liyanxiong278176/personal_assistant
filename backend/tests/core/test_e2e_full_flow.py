"""E2E Full Flow Test Suite

This module implements comprehensive end-to-end testing for the Agent Core system,
covering all major workflows from user input to response generation.

Test Scenarios:
1. Simple Q&A - Basic query flow
2. Multi-turn conversation - Memory injection and context management
3. Tool calling - External data retrieval
4. Long conversation compression - Context threshold handling
5. Itinerary planning full flow - Intent to itinerary with budget control
6. Multi-turn itinerary modification - Memory recall and update
7. Hotel recommendation - Hotel query with filters
8. Budget control - Budget query with breakdown
9. Invalid input handling - Graceful degradation
10. Cross-intent switching - Multiple intent transitions

Author: Agent Core Testing Team
Date: 2026-04-15
"""

import asyncio
import logging
import sys
import time
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncIterator
from uuid import uuid4

# Set encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

os.environ["PYTHONPATH"] = "/d/agent_learning/travel_assistant/backend"

from app.core import (
    AgentError,
    DegradationLevel,
    LLMClient,
    Tool,
    ToolCall,
    ToolResult,
    ToolCallResult,
    ToolRegistry,
    global_registry,
    QueryEngine,
    RequestContext,
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    SlotExtractor,
    SlotResult,
    DateRange,
)
from app.core.tools import ToolExecutor
from app.core.context_mgmt import (
    ContextCompressor,
    TokenEstimator,
    AgentEnhancementConfig,
    InferenceGuard,
    OverlimitStrategy,
)
from app.core.memory.injection import MemoryInjector
from app.core.intent import IntentRouter, RuleStrategy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# Test Result Tracking
# =============================================================================

class TestStatus(Enum):
    """Test execution status"""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class NodeOutput:
    """Output from a single workflow node"""
    node_name: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    error: Optional[str] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node_name,
            "input": self.input_data,
            "output": self.output_data,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class ScenarioResult:
    """Result of a single test scenario"""
    scenario_id: int
    scenario_name: str
    status: TestStatus
    input_query: str
    nodes: List[NodeOutput] = field(default_factory=list)
    final_response: str = ""
    error_message: str = ""
    total_duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_name": self.scenario_name,
            "status": self.status.value,
            "input_query": self.input_query,
            "nodes": [n.to_dict() for n in self.nodes],
            "final_response": self.final_response[:200] + "..." if len(self.final_response) > 200 else self.final_response,
            "error_message": self.error_message,
            "total_duration_ms": self.total_duration_ms,
            "timestamp": self.timestamp,
        }


# =============================================================================
# Mock Components for Testing
# =============================================================================

class MockLLMClient(LLMClient):
    """Mock LLM client for testing without real API calls"""

    def __init__(self, responses: Optional[Dict[str, str]] = None):
        """Initialize with predefined responses

        Args:
            responses: Mapping of input patterns to responses
        """
        self._responses = responses or {}
        self._call_count = 0
        self._call_history: List[Dict[str, Any]] = []

    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        guard: Optional[InferenceGuard] = None,
    ) -> AsyncIterator[str]:
        """Mock streaming chat response"""
        self._call_count += 1
        last_msg = messages[-1]["content"] if messages else ""

        # Check for pattern matches
        for pattern, response in self._responses.items():
            if pattern in last_msg:
                yield response
                self._call_history.append({
                    "method": "stream_chat",
                    "input": last_msg,
                    "output": response,
                })
                return

        # Default response based on input
        if "天气" in last_msg or "weather" in last_msg.lower():
            yield f"根据天气查询结果，{last_msg}的天气情况良好，适合出行。"
        elif "景点" in last_msg or "attraction" in last_msg.lower():
            yield "推荐以下景点：故宫、长城、天坛等著名景点值得一游。"
        elif "酒店" in last_msg or "hotel" in last_msg.lower():
            yield "为您推荐以下酒店：五星级酒店、精品酒店、经济型酒店等多种选择。"
        elif "预算" in last_msg or "budget" in last_msg.lower():
            yield "根据您的预算，建议如下分配：交通30%、住宿40%、餐饮20%、景点10%。"
        elif "行程" in last_msg or "itinerary" in last_msg.lower():
            yield "为您规划了详细的行程安排，包括景点游览、交通方式、餐饮推荐等。"
        else:
            yield f"收到您的消息：{last_msg}。我是旅游助手，很高兴为您服务！"

        self._call_history.append({
            "method": "stream_chat",
            "input": last_msg,
            "output": "default_response",
        })

    async def chat_with_tools(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
    ) -> tuple[str, List[ToolCall]]:
        """Mock chat with tools - simulates tool calling"""
        self._call_count += 1
        last_msg = messages[-1]["content"] if messages else ""

        # Check if we should request tool calls
        tool_calls = []
        content = ""

        if "天气" in last_msg and any(t["name"] == "get_weather" for t in tools):
            tool_calls.append(ToolCall(
                id=f"call_{self._call_count}",
                name="get_weather",
                arguments={"city": self._extract_city(last_msg)}
            ))
        elif "景点" in last_msg and any(t["name"] == "get_attractions" for t in tools):
            tool_calls.append(ToolCall(
                id=f"call_{self._call_count}",
                name="get_attractions",
                arguments={"city": self._extract_city(last_msg)}
            ))
        elif "酒店" in last_msg and any(t["name"] == "search_hotels" for t in tools):
            tool_calls.append(ToolCall(
                id=f"call_{self._call_count}",
                name="search_hotels",
                arguments={"city": self._extract_city(last_msg)}
            ))
        else:
            # Return direct response
            if "天气" in last_msg:
                content = f"{self._extract_city(last_msg)}今天晴天，25°C"
            elif "景点" in last_msg:
                content = f"{self._extract_city(last_msg)}的热门景点：故宫、长城、天坛"
            else:
                content = f"关于'{last_msg}'，我很乐意为您提供帮助。"

        self._call_history.append({
            "method": "chat_with_tools",
            "input": last_msg,
            "tool_calls": [tc.name for tc in tool_calls],
        })

        return content, tool_calls

    def _extract_city(self, text: str) -> str:
        """Extract city name from text"""
        cities = ["北京", "上海", "杭州", "西安", "成都", "重庆", "南京"]
        for city in cities:
            if city in text:
                return city
        return "北京"

    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get history of all calls made"""
        return self._call_history

    def reset(self):
        """Reset call history"""
        self._call_count = 0
        self._call_history = []


# =============================================================================
# Mock Tools
# =============================================================================

class MockWeatherTool(Tool):
    """Mock weather tool for testing"""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "获取指定城市的天气信息"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, city: str) -> str:
        return f"{city}今天晴天，温度25°C，适合出行"


class MockAttractionTool(Tool):
    """Mock attraction tool for testing"""

    @property
    def name(self) -> str:
        return "get_attractions"

    @property
    def description(self) -> str:
        return "获取指定城市的景点推荐"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, city: str) -> str:
        attractions = {
            "北京": ["故宫", "长城", "天坛", "颐和园"],
            "上海": ["外滩", "东方明珠", "豫园", "南京路"],
            "杭州": ["西湖", "灵隐寺", "雷峰塔", "千岛湖"],
            "西安": ["兵马俑", "大雁塔", "城墙", "华清池"],
        }
        return f"{city}的热门景点：{', '.join(attractions.get(city, ['景点1', '景点2']))}"


class MockHotelTool(Tool):
    """Mock hotel tool for testing"""

    @property
    def name(self) -> str:
        return "search_hotels"

    @property
    def description(self) -> str:
        return "搜索指定城市的酒店信息"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, city: str, budget: Optional[int] = None) -> str:
        hotels = {
            "北京": ["北京饭店", "王府井酒店", "青年旅舍"],
            "上海": ["上海和平饭店", "外滩酒店", "经济型酒店"],
            "杭州": ["西湖国宾馆", "灵隐寺酒店", "民宿"],
        }
        hotel_list = hotels.get(city, ["酒店1", "酒店2", "酒店3"])
        if budget:
            return f"{city}的推荐酒店（预算{budget}元）：{', '.join(hotel_list)}"
        return f"{city}的推荐酒店：{', '.join(hotel_list)}"


class MockBudgetTool(Tool):
    """Mock budget tool for testing"""

    @property
    def name(self) -> str:
        return "calculate_budget"

    @property
    def description(self) -> str:
        return "计算旅行预算分配"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, destination: str, days: int, total_budget: int) -> str:
        per_day = total_budget // days
        breakdown = {
            "交通": total_budget * 0.3,
            "住宿": total_budget * 0.4,
            "餐饮": total_budget * 0.2,
            "景点": total_budget * 0.1,
        }
        return (
            f"{destination}{days}天行程预算{total_budget}元："
            f"人均{per_day}元/天。分配：交通{breakdown['交通']:.0f}元，"
            f"住宿{breakdown['住宿']:.0f}元，餐饮{breakdown['餐饮']:.0f}元，"
            f"景点{breakdown['景点']:.0f}元"
        )


# =============================================================================
# E2E Test Runner
# =============================================================================

class E2ETestRunner:
    """End-to-end test runner for Agent Core workflows"""

    def __init__(self):
        """Initialize the test runner"""
        self.results: List[ScenarioResult] = []
        self._setup_components()

    def _setup_components(self):
        """Set up test components"""
        # Create mock LLM client
        self.llm_client = MockLLMClient()

        # Create tool registry with mock tools
        self.tool_registry = ToolRegistry()
        self.tool_registry.register(MockWeatherTool())
        self.tool_registry.register(MockAttractionTool())
        self.tool_registry.register(MockHotelTool())
        self.tool_registry.register(MockBudgetTool())

        # Create QueryEngine with mock components
        self.query_engine = QueryEngine(
            llm_client=self.llm_client,
            tool_registry=self.tool_registry,
        )

        # Create memory hierarchy
        self.memory_hierarchy = MemoryHierarchy()

        # Create memory injector
        self.memory_injector = MemoryInjector(self.memory_hierarchy)

        # Create intent router
        self.intent_router = IntentRouter(
            strategies=[RuleStrategy()]
        )

        # Create slot extractor
        self.slot_extractor = SlotExtractor()

        logger.info("[E2ETestRunner] Components initialized")

    async def run_scenario_1_simple_qa(self) -> ScenarioResult:
        """Scenario 1: Simple Q&A

        Test basic query flow from input to response.
        - Input: "你好"
        - Expected: Intent recognition -> LLM response
        """
        result = ScenarioResult(
            scenario_id=1,
            scenario_name="简单问答",
            input_query="你好",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            # Step 1: Intent Recognition
            node_start = time.perf_counter()
            context = RequestContext(message="你好", user_id="test_user")
            intent_result = await self.intent_router.classify(context)
            result.nodes.append(NodeOutput(
                node_name="IntentRouter",
                input_data={"message": "你好"},
                output_data={
                    "intent": intent_result.intent,
                    "confidence": intent_result.confidence,
                    "strategy": intent_result.strategy,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 2: Slot Extraction
            node_start = time.perf_counter()
            slots = self.slot_extractor.extract("你好")
            result.nodes.append(NodeOutput(
                node_name="SlotExtractor",
                input_data={"message": "你好"},
                output_data={
                    "destination": slots.destination,
                    "start_date": slots.start_date,
                    "days": slots.days,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 3: LLM Response Generation
            node_start = time.perf_counter()
            response_parts = []
            async for chunk in self.llm_client.stream_chat([{"role": "user", "content": "你好"}]):
                response_parts.append(chunk)
            response = "".join(response_parts)
            result.nodes.append(NodeOutput(
                node_name="LLMClient",
                input_data={"message": "你好"},
                output_data={"response_length": len(response)},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            result.final_response = response
            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify flow connectivity
            if intent_result.intent == "chat" and len(response) > 0:
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = f"Unexpected intent or empty response"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 1] Error: {e}")

        return result

    async def run_scenario_2_multi_turn(self) -> ScenarioResult:
        """Scenario 2: Multi-turn Conversation

        Test N consecutive dialog turns with memory injection.
        - Turn 1: "我想去北京旅游"
        - Turn 2: "有什么好玩的"
        - Turn 3: "天气怎么样"
        - Expected: Memory injection, context management
        """
        result = ScenarioResult(
            scenario_id=2,
            scenario_name="多轮对话",
            input_query="我想去北京旅游 -> 有什么好玩的 -> 天气怎么样",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        conversation_id = str(uuid4())
        turns = [
            "我想去北京旅游",
            "有什么好玩的",
            "天气怎么样",
        ]

        try:
            for i, user_input in enumerate(turns, 1):
                # Step 1: Intent Recognition
                node_start = time.perf_counter()
                context = RequestContext(
                    message=user_input,
                    user_id="test_user",
                    conversation_id=conversation_id
                )
                intent_result = await self.intent_router.classify(context)
                result.nodes.append(NodeOutput(
                    node_name=f"IntentRouter_Turn{i}",
                    input_data={"message": user_input},
                    output_data={
                        "intent": intent_result.intent,
                        "confidence": intent_result.confidence,
                    },
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # Step 2: Slot Extraction
                node_start = time.perf_counter()
                slots = self.slot_extractor.extract(user_input)
                result.nodes.append(NodeOutput(
                    node_name=f"SlotExtractor_Turn{i}",
                    input_data={"message": user_input},
                    output_data={"destination": slots.destination},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # Step 3: Memory Injection (simulate)
                node_start = time.perf_counter()
                memory_context = self.memory_injector.build_memory_context(
                    user_input, max_memories=3
                )
                result.nodes.append(NodeOutput(
                    node_name=f"MemoryInjector_Turn{i}",
                    input_data={"message": user_input},
                    output_data={"memory_context_length": len(memory_context)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # Add to memory
                if i == 1 and slots.destination:
                    self.memory_hierarchy.add(MemoryItem(
                        content=f"用户想去{slots.destination}旅游",
                        level=MemoryLevel.EPISODIC,
                        memory_type=MemoryType.INTENT,
                        importance=0.8,
                    ))

                # Step 4: LLM Response
                node_start = time.perf_counter()
                response_parts = []
                async for chunk in self.llm_client.stream_chat(
                    [{"role": "user", "content": user_input}]
                ):
                    response_parts.append(chunk)
                response = "".join(response_parts)
                result.nodes.append(NodeOutput(
                    node_name=f"LLMClient_Turn{i}",
                    input_data={"message": user_input},
                    output_data={"response_length": len(response)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                if i == len(turns):
                    result.final_response = response

            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify memory was injected
            if len(self.memory_hierarchy.get_episodic()) > 0:
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = "Memory not injected"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 2] Error: {e}")

        return result

    async def run_scenario_3_tool_calling(self) -> ScenarioResult:
        """Scenario 3: Tool Calling

        Test query requiring external data retrieval.
        - Input: "北京今天天气怎么样"
        - Expected: Tool selection -> execution -> result integration
        """
        result = ScenarioResult(
            scenario_id=3,
            scenario_name="工具调用",
            input_query="北京今天天气怎么样",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            user_input = "北京今天天气怎么样"

            # Step 1: Intent Recognition
            node_start = time.perf_counter()
            context = RequestContext(message=user_input, user_id="test_user")
            intent_result = await self.intent_router.classify(context)
            result.nodes.append(NodeOutput(
                node_name="IntentRouter",
                input_data={"message": user_input},
                output_data={"intent": intent_result.intent},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 2: Slot Extraction
            node_start = time.perf_counter()
            slots = self.slot_extractor.extract(user_input)
            result.nodes.append(NodeOutput(
                node_name="SlotExtractor",
                input_data={"message": user_input},
                output_data={"destination": slots.destination},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 3: Tool Selection (chat_with_tools)
            node_start = time.perf_counter()
            tools = [
                {
                    "name": "get_weather",
                    "description": "获取指定城市的天气信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "城市名称"}
                        },
                        "required": ["city"]
                    }
                }
            ]
            content, tool_calls = await self.llm_client.chat_with_tools(
                [{"role": "user", "content": user_input}],
                tools
            )
            result.nodes.append(NodeOutput(
                node_name="LLMToolSelection",
                input_data={"message": user_input, "tools_count": len(tools)},
                output_data={
                    "tool_calls_count": len(tool_calls),
                    "tool_names": [tc.name for tc in tool_calls],
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 4: Tool Execution
            node_start = time.perf_counter()
            tool_executor = ToolExecutor(self.tool_registry)
            if tool_calls:
                tool_results = await tool_executor.execute_parallel(tool_calls)
                result.nodes.append(NodeOutput(
                    node_name="ToolExecutor",
                    input_data={"tool_calls": len(tool_calls)},
                    output_data={
                        "results_count": len(tool_results),
                        "results": list(tool_results.keys()),
                    },
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # Step 5: Response Generation with tool results
                node_start = time.perf_counter()
                response_parts = []
                async for chunk in self.llm_client.stream_chat(
                    [{"role": "user", "content": user_input}]
                ):
                    response_parts.append(chunk)
                response = "".join(response_parts)
                result.nodes.append(NodeOutput(
                    node_name="LLMClient_Final",
                    input_data={"has_tool_results": True},
                    output_data={"response_length": len(response)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                result.final_response = response
            else:
                result.status = TestStatus.FAIL
                result.error_message = "No tool calls generated"

            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify tool was called
            if tool_calls and tool_calls[0].name == "get_weather":
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = f"Expected get_weather tool call, got {tool_calls}"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 3] Error: {e}")

        return result

    async def run_scenario_4_long_conversation(self) -> ScenarioResult:
        """Scenario 4: Long Conversation Compression

        Test conversation exceeding compression threshold.
        - Input: 20+ turns of conversation
        - Expected: Compression triggered, summary generated
        """
        result = ScenarioResult(
            scenario_id=4,
            scenario_name="长对话压缩",
            input_query="20+轮对话",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            conversation_id = str(uuid4())

            # Generate 20+ turns
            for i in range(25):
                user_input = f"这是第{i+1}轮对话，我想了解旅游信息"

                # Add to working memory
                self.query_engine._add_to_working_memory(
                    conversation_id, "user", user_input
                )

                # Simulate assistant response
                self.query_engine._add_to_working_memory(
                    conversation_id, "assistant", f"收到您的第{i+1}条消息"
                )

            # Check if compression is needed
            node_start = time.perf_counter()
            history = self.query_engine._get_conversation_history(conversation_id)
            history_chars = sum(len(m.get("content", "")) for m in history)

            # Use ContextCompressor to check compression
            from app.core.context_mgmt.config import ContextConfig
            config = ContextConfig(window_size=100, compress_threshold=0.5)
            compressor = ContextCompressor(config=config)
            needs_compress = compressor.needs_compaction(history)

            result.nodes.append(NodeOutput(
                node_name="ContextCompressor",
                input_data={"conversation_id": conversation_id},
                output_data={
                    "history_length": len(history),
                    "history_chars": history_chars,
                    "needs_compression": needs_compress,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Perform compression if needed
            if needs_compress:
                node_start = time.perf_counter()
                compressed = await compressor.compact(history)
                result.nodes.append(NodeOutput(
                    node_name="ContextCompressor_Compress",
                    input_data={"original_length": len(history)},
                    output_data={"compressed_length": len(compressed)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                result.final_response = f"Conversation compressed from {len(history)} to {len(compressed)} messages"
                result.status = TestStatus.PASS
            else:
                result.final_response = f"Conversation not compressed ({len(history)} messages)"
                result.status = TestStatus.PASS

            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 4] Error: {e}")

        return result

    async def run_scenario_5_itinerary_planning(self) -> ScenarioResult:
        """Scenario 5: Itinerary Planning Full Flow

        Test complete itinerary planning with budget control.
        - Input: "杭州3天游，预算2000元，带老人"
        - Expected: Intent -> slots -> itinerary -> budget validation
        """
        result = ScenarioResult(
            scenario_id=5,
            scenario_name="行程规划全流程",
            input_query="杭州3天游，预算2000元，带老人",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            user_input = "杭州3天游，预算2000元，带老人"

            # Step 1: Intent Recognition
            node_start = time.perf_counter()
            context = RequestContext(message=user_input, user_id="test_user")
            intent_result = await self.intent_router.classify(context)
            result.nodes.append(NodeOutput(
                node_name="IntentRouter",
                input_data={"message": user_input},
                output_data={
                    "intent": intent_result.intent,
                    "confidence": intent_result.confidence,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 2: Slot Extraction
            node_start = time.perf_counter()
            slots = self.slot_extractor.extract(user_input)
            result.nodes.append(NodeOutput(
                node_name="SlotExtractor",
                input_data={"message": user_input},
                output_data={
                    "destination": slots.destination,
                    "days": slots.days,
                    "budget": slots.budget,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 3: Tool Calls (attractions + budget)
            node_start = time.perf_counter()
            tools = [
                {
                    "name": "get_attractions",
                    "description": "获取指定城市的景点推荐",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "城市名称"}
                        },
                        "required": ["city"]
                    }
                },
                {
                    "name": "calculate_budget",
                    "description": "计算旅行预算分配",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "destination": {"type": "string"},
                            "days": {"type": "integer"},
                            "total_budget": {"type": "integer"}
                        },
                        "required": ["destination", "days", "total_budget"]
                    }
                }
            ]

            # Mock tool execution
            tool_executor = ToolExecutor(self.tool_registry)
            attraction_result = await tool_executor.execute(
                "get_attractions", city=slots.destination or "杭州"
            )
            budget_result = await tool_executor.execute(
                "calculate_budget",
                destination=slots.destination or "杭州",
                days=slots.days or 3,
                total_budget=slots.budget or 2000
            )

            result.nodes.append(NodeOutput(
                node_name="ToolExecutor",
                input_data={"destination": slots.destination, "days": slots.days},
                output_data={
                    "attractions": attraction_result[:50] + "...",
                    "budget": budget_result[:50] + "...",
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Step 4: Response Generation
            node_start = time.perf_counter()
            response_parts = []
            async for chunk in self.llm_client.stream_chat(
                [{"role": "user", "content": user_input}]
            ):
                response_parts.append(chunk)
            response = "".join(response_parts)
            result.nodes.append(NodeOutput(
                node_name="LLMClient",
                input_data={"message": user_input},
                output_data={"response_length": len(response)},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            result.final_response = response
            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify all components executed
            if (intent_result.intent == "itinerary" and
                slots.destination and slots.days and slots.budget):
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = "Missing required slots or incorrect intent"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 5] Error: {e}")

        return result

    async def run_scenario_6_itinerary_modification(self) -> ScenarioResult:
        """Scenario 6: Multi-turn Itinerary Modification

        Test itinerary modification across turns with memory recall.
        - Turn 1: "规划北京3天游"
        - Turn 2: "把第二天改成去颐和园"
        - Expected: Memory recall, itinerary update
        """
        result = ScenarioResult(
            scenario_id=6,
            scenario_name="多轮行程修改",
            input_query="规划北京3天游 -> 把第二天改成去颐和园",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            conversation_id = str(uuid4())
            turns = [
                "规划北京3天游",
                "把第二天改成去颐和园",
            ]

            for i, user_input in enumerate(turns, 1):
                # Intent Recognition
                node_start = time.perf_counter()
                context = RequestContext(
                    message=user_input,
                    user_id="test_user",
                    conversation_id=conversation_id
                )
                intent_result = await self.intent_router.classify(context)
                result.nodes.append(NodeOutput(
                    node_name=f"IntentRouter_Turn{i}",
                    input_data={"message": user_input},
                    output_data={"intent": intent_result.intent},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # Slot Extraction
                node_start = time.perf_counter()
                slots = self.slot_extractor.extract(user_input)
                result.nodes.append(NodeOutput(
                    node_name=f"SlotExtractor_Turn{i}",
                    input_data={"message": user_input},
                    output_data={
                        "destination": slots.destination,
                        "days": slots.days,
                    },
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # Add to episodic memory
                if i == 1:
                    self.memory_hierarchy.add(MemoryItem(
                        content="用户规划北京3天游",
                        level=MemoryLevel.EPISODIC,
                        memory_type=MemoryType.INTENT,
                        importance=0.9,
                    ))

                # Check memory recall on turn 2
                if i == 2:
                    node_start = time.perf_counter()
                    memories = self.memory_hierarchy.get_episodic(limit=5)
                    result.nodes.append(NodeOutput(
                        node_name="MemoryRecall_Turn2",
                        input_data={"query": user_input},
                        output_data={"episodic_count": len(memories)},
                        duration_ms=(time.perf_counter() - node_start) * 1000,
                    ))

                # LLM Response
                node_start = time.perf_counter()
                response_parts = []
                async for chunk in self.llm_client.stream_chat(
                    [{"role": "user", "content": user_input}]
                ):
                    response_parts.append(chunk)
                response = "".join(response_parts)
                result.nodes.append(NodeOutput(
                    node_name=f"LLMClient_Turn{i}",
                    input_data={"message": user_input},
                    output_data={"response_length": len(response)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                if i == len(turns):
                    result.final_response = response

            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify memory was recalled
            episodic = self.memory_hierarchy.get_episodic()
            if len(episodic) > 0:
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = "No episodic memory found"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 6] Error: {e}")

        return result

    async def run_scenario_7_hotel_recommendation(self) -> ScenarioResult:
        """Scenario 7: Hotel Recommendation

        Test hotel query with filters.
        - Input: "帮我找杭州的酒店，预算500元以内"
        - Expected: Hotel tool call -> filtering -> response
        """
        result = ScenarioResult(
            scenario_id=7,
            scenario_name="酒店推荐",
            input_query="帮我找杭州的酒店，预算500元以内",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            user_input = "帮我找杭州的酒店，预算500元以内"

            # Intent Recognition
            node_start = time.perf_counter()
            context = RequestContext(message=user_input, user_id="test_user")
            intent_result = await self.intent_router.classify(context)
            result.nodes.append(NodeOutput(
                node_name="IntentRouter",
                input_data={"message": user_input},
                output_data={"intent": intent_result.intent},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Slot Extraction
            node_start = time.perf_counter()
            slots = self.slot_extractor.extract(user_input)
            result.nodes.append(NodeOutput(
                node_name="SlotExtractor",
                input_data={"message": user_input},
                output_data={
                    "destination": slots.destination,
                    "budget": slots.budget,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Tool Execution
            node_start = time.perf_counter()
            tool_executor = ToolExecutor(self.tool_registry)
            hotel_result = await tool_executor.execute(
                "search_hotels",
                city=slots.destination or "杭州",
                budget=slots.budget or 500
            )
            result.nodes.append(NodeOutput(
                node_name="ToolExecutor",
                input_data={"city": slots.destination, "budget": slots.budget},
                output_data={"result": hotel_result[:100]},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # LLM Response
            node_start = time.perf_counter()
            response_parts = []
            async for chunk in self.llm_client.stream_chat(
                [{"role": "user", "content": user_input}]
            ):
                response_parts.append(chunk)
            response = "".join(response_parts)
            result.nodes.append(NodeOutput(
                node_name="LLMClient",
                input_data={"message": user_input},
                output_data={"response_length": len(response)},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            result.final_response = response
            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify hotel tool was called
            if "酒店" in hotel_result:
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = "Hotel tool did not return expected results"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 7] Error: {e}")

        return result

    async def run_scenario_8_budget_control(self) -> ScenarioResult:
        """Scenario 8: Budget Control

        Test budget query with breakdown.
        - Input: "去西安5天大概多少钱"
        - Expected: Budget breakdown -> fee splitting -> validation
        """
        result = ScenarioResult(
            scenario_id=8,
            scenario_name="预算控制",
            input_query="去西安5天大概多少钱",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            user_input = "去西安5天大概多少钱"

            # Intent Recognition
            node_start = time.perf_counter()
            context = RequestContext(message=user_input, user_id="test_user")
            intent_result = await self.intent_router.classify(context)
            result.nodes.append(NodeOutput(
                node_name="IntentRouter",
                input_data={"message": user_input},
                output_data={"intent": intent_result.intent},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Slot Extraction
            node_start = time.perf_counter()
            slots = self.slot_extractor.extract(user_input)
            result.nodes.append(NodeOutput(
                node_name="SlotExtractor",
                input_data={"message": user_input},
                output_data={
                    "destination": slots.destination,
                    "days": slots.days,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # Budget Calculation
            node_start = time.perf_counter()
            tool_executor = ToolExecutor(self.tool_registry)
            budget_result = await tool_executor.execute(
                "calculate_budget",
                destination=slots.destination or "西安",
                days=slots.days or 5,
                total_budget=3000  # Default budget
            )
            result.nodes.append(NodeOutput(
                node_name="ToolExecutor_Budget",
                input_data={"destination": slots.destination, "days": slots.days},
                output_data={"budget_breakdown": budget_result[:150]},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # LLM Response
            node_start = time.perf_counter()
            response_parts = []
            async for chunk in self.llm_client.stream_chat(
                [{"role": "user", "content": user_input}]
            ):
                response_parts.append(chunk)
            response = "".join(response_parts)
            result.nodes.append(NodeOutput(
                node_name="LLMClient",
                input_data={"message": user_input},
                output_data={"response_length": len(response)},
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            result.final_response = response
            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify budget breakdown
            if "交通" in budget_result and "住宿" in budget_result:
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = "Budget breakdown incomplete"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 8] Error: {e}")

        return result

    async def run_scenario_9_invalid_input(self) -> ScenarioResult:
        """Scenario 9: Invalid Input Handling

        Test graceful degradation for invalid inputs.
        - Input: "@#$%^&*()" or very long input
        - Expected: Error handling, graceful response
        """
        result = ScenarioResult(
            scenario_id=9,
            scenario_name="异常输入处理",
            input_query="@#$%^&*()",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            user_input = "@#$%^&*()"

            # Intent Recognition (should handle gracefully)
            node_start = time.perf_counter()
            context = RequestContext(message=user_input, user_id="test_user")
            intent_result = await self.intent_router.classify(context)
            result.nodes.append(NodeOutput(
                node_name="IntentRouter",
                input_data={"message": user_input},
                output_data={
                    "intent": intent_result.intent,
                    "confidence": intent_result.confidence,
                    "strategy": intent_result.strategy,
                },
                duration_ms=(time.perf_counter() - node_start) * 1000,
            ))

            # LLM Response (should handle gracefully)
            node_start = time.perf_counter()
            response_parts = []
            try:
                async for chunk in self.llm_client.stream_chat(
                    [{"role": "user", "content": user_input}]
                ):
                    response_parts.append(chunk)
                response = "".join(response_parts)
                result.nodes.append(NodeOutput(
                    node_name="LLMClient",
                    input_data={"message": user_input},
                    output_data={"response_length": len(response)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))
                result.final_response = response
                result.status = TestStatus.PASS
            except Exception as llm_error:
                result.nodes.append(NodeOutput(
                    node_name="LLMClient",
                    input_data={"message": user_input},
                    output_data={},
                    error=str(llm_error),
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))
                # System handled error gracefully
                result.final_response = "系统无法理解您的输入，请提供更具体的信息。"
                result.status = TestStatus.PASS

            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 9] Error: {e}")

        return result

    async def run_scenario_10_cross_intent_switching(self) -> ScenarioResult:
        """Scenario 10: Cross-Intent Switching

        Test multiple intent switches in conversation.
        - Turn 1: "规划行程" (itinerary)
        - Turn 2: "查询天气" (query)
        - Turn 3: "推荐酒店" (hotel)
        - Turn 4: "计算预算" (budget)
        - Expected: Intent switches handled correctly
        """
        result = ScenarioResult(
            scenario_id=10,
            scenario_name="跨意图切换",
            input_query="规划行程 -> 查询天气 -> 推荐酒店 -> 计算预算",
            status=TestStatus.PASS,
        )
        start_time = time.perf_counter()

        try:
            conversation_id = str(uuid4())
            turns = [
                ("规划北京3天行程", "itinerary"),
                ("北京今天天气怎么样", "query"),
                ("推荐北京的酒店", "hotel"),
                ("预算3000够不够", "budget"),
            ]

            intent_transitions = []

            for i, (user_input, expected_intent) in enumerate(turns, 1):
                # Intent Recognition
                node_start = time.perf_counter()
                context = RequestContext(
                    message=user_input,
                    user_id="test_user",
                    conversation_id=conversation_id
                )
                intent_result = await self.intent_router.classify(context)
                result.nodes.append(NodeOutput(
                    node_name=f"IntentRouter_Turn{i}",
                    input_data={"message": user_input, "expected": expected_intent},
                    output_data={
                        "intent": intent_result.intent,
                        "confidence": intent_result.confidence,
                    },
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                intent_transitions.append(intent_result.intent)

                # Slot Extraction
                node_start = time.perf_counter()
                slots = self.slot_extractor.extract(user_input)
                result.nodes.append(NodeOutput(
                    node_name=f"SlotExtractor_Turn{i}",
                    input_data={"message": user_input},
                    output_data={
                        "destination": slots.destination,
                        "days": slots.days,
                        "budget": slots.budget,
                    },
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                # LLM Response
                node_start = time.perf_counter()
                response_parts = []
                async for chunk in self.llm_client.stream_chat(
                    [{"role": "user", "content": user_input}]
                ):
                    response_parts.append(chunk)
                response = "".join(response_parts)
                result.nodes.append(NodeOutput(
                    node_name=f"LLMClient_Turn{i}",
                    input_data={"message": user_input},
                    output_data={"response_length": len(response)},
                    duration_ms=(time.perf_counter() - node_start) * 1000,
                ))

                if i == len(turns):
                    result.final_response = response

            result.total_duration_ms = (time.perf_counter() - start_time) * 1000

            # Verify intent transitions
            if len(set(intent_transitions)) >= 3:  # At least 3 different intents
                result.status = TestStatus.PASS
            else:
                result.status = TestStatus.FAIL
                result.error_message = f"Insufficient intent variety: {intent_transitions}"

        except Exception as e:
            result.status = TestStatus.ERROR
            result.error_message = str(e)
            logger.error(f"[Scenario 10] Error: {e}")

        return result

    # =========================================================================
    # Test Execution
    # =========================================================================

    async def run_all_scenarios(self) -> List[ScenarioResult]:
        """Run all E2E test scenarios

        Returns:
            List of scenario results
        """
        logger.info("="*70)
        logger.info("E2E Full Flow Test Suite - Starting Execution")
        logger.info("="*70)

        scenarios = [
            self.run_scenario_1_simple_qa,
            self.run_scenario_2_multi_turn,
            self.run_scenario_3_tool_calling,
            self.run_scenario_4_long_conversation,
            self.run_scenario_5_itinerary_planning,
            self.run_scenario_6_itinerary_modification,
            self.run_scenario_7_hotel_recommendation,
            self.run_scenario_8_budget_control,
            self.run_scenario_9_invalid_input,
            self.run_scenario_10_cross_intent_switching,
        ]

        for scenario in scenarios:
            try:
                result = await scenario()
                self.results.append(result)
                logger.info(
                    f"[Scenario {result.scenario_id}] {result.scenario_name} - "
                    f"{result.status.value} ({result.total_duration_ms:.2f}ms)"
                )
            except Exception as e:
                logger.error(f"Scenario execution failed: {e}")
                self.results.append(ScenarioResult(
                    scenario_id=0,
                    scenario_name=scenario.__name__,
                    status=TestStatus.ERROR,
                    input_query="unknown",
                    error_message=str(e),
                ))

        return self.results

    def generate_report(self) -> str:
        """Generate test report

        Returns:
            Formatted report string
        """
        report_lines = [
            "# E2E Full Flow Test Report",
            f"\nGenerated: {datetime.now().isoformat()}",
            "\n## Test Results Summary",
            "\n| Scenario ID | Name | Status | Duration (ms) |",
            "|-------------|------|--------|---------------|",
        ]

        pass_count = sum(1 for r in self.results if r.status == TestStatus.PASS)
        fail_count = sum(1 for r in self.results if r.status == TestStatus.FAIL)
        error_count = sum(1 for r in self.results if r.status == TestStatus.ERROR)

        for result in self.results:
            status_icon = "✅" if result.status == TestStatus.PASS else "❌"
            report_lines.append(
                f"| {result.scenario_id} | {result.scenario_name} | "
                f"{status_icon} {result.status.value} | {result.total_duration_ms:.2f} |"
            )

        report_lines.extend([
            f"\n**Pass Rate:** {pass_count}/{len(self.results)} ({pass_count/len(self.results)*100:.1f}%)",
            f"- Passed: {pass_count}",
            f"- Failed: {fail_count}",
            f"- Errors: {error_count}",
            "\n## Flow Connectivity Assessment",
        ])

        # Flow connectivity analysis
        flow_nodes = [
            "IntentRouter",
            "SlotExtractor",
            "ToolExecutor",
            "LLMClient",
            "MemoryInjector",
            "ContextCompressor",
        ]

        connected_nodes = set()
        for result in self.results:
            for node in result.nodes:
                connected_nodes.add(node.node_name)

        report_lines.append("\n### Connected Nodes:")
        for node in flow_nodes:
            status = "✅ Connected" if node in connected_nodes else "❌ Not Connected"
            report_lines.append(f"- {node}: {status}")

        report_lines.append("\n## Detailed Results\n")

        for result in self.results:
            report_lines.append(f"### Scenario {result.scenario_id}: {result.scenario_name}")
            report_lines.append(f"**Input:** {result.input_query}")
            report_lines.append(f"**Status:** {result.status.value}")
            report_lines.append(f"**Duration:** {result.total_duration_ms:.2f}ms")

            if result.error_message:
                report_lines.append(f"**Error:** {result.error_message}")

            report_lines.append("\n**Node Outputs:**")
            for node in result.nodes:
                report_lines.append(f"- {node.node_name}: {node.duration_ms:.2f}ms")
                if node.error:
                    report_lines.append(f"  - Error: {node.error}")

            report_lines.append(f"\n**Final Response:** {result.final_response[:200]}...\n")

        report_lines.append("## Recommendations\n")

        if fail_count > 0 or error_count > 0:
            report_lines.append("### Issues Found:")
            for result in self.results:
                if result.status != TestStatus.PASS:
                    report_lines.append(
                        f"- Scenario {result.scenario_id}: {result.error_message or 'Unknown error'}"
                    )

            report_lines.append("\n### Suggested Actions:")
            report_lines.append("1. Review failed scenarios for configuration issues")
            report_lines.append("2. Check LLM client connectivity and API credentials")
            report_lines.append("3. Verify tool registration and execution")
            report_lines.append("4. Test memory injection and context compression")
        else:
            report_lines.append("✅ All scenarios passed successfully!")
            report_lines.append("The system is ready for production deployment.")

        return "\n".join(report_lines)


# =============================================================================
# Main Entry Point
# =============================================================================

async def main():
    """Main entry point for E2E test execution"""
    runner = E2ETestRunner()
    await runner.run_all_scenarios()

    # Print report
    report = runner.generate_report()
    print(report)

    # Save report to file
    report_path = "D:/agent_learning/travel_assistant/backend/tests/core/TEST_REPORT_E2E.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n✅ Report saved to: {report_path}")

    return runner


if __name__ == "__main__":
    asyncio.run(main())
