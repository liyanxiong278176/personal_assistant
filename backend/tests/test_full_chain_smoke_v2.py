#!/usr/bin/env python3
"""
AI旅行助手 - 全链路核心功能冒烟回归测试 v2
Phase 2: 验证修复代码未破坏核心主流程

基于实际API调整的测试版本
"""

import asyncio
import sys
import time
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import httpx


# 测试配置
BASE_URL = "http://localhost:8000"
TEST_USER = {
    "email": "2781764566@qq.com",
    "password": "123456"
}
TEST_REQUEST = "我想4月20号到25号去成都玩，2个人，预算6000，帮我规划行程、查酒店、看天气、做预算分配"


class TestPhase2APIEndpoints:
    """Phase 2: API接口可用性测试"""

    @pytest.mark.asyncio
    async def test_01_health_check(self):
        """���证服务健康状态"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            print(f"✓ Health check passed")

    @pytest.mark.asyncio
    async def test_02_root_endpoint(self):
        """测试根端���"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/")
            assert response.status_code == 200
            data = response.json()
            assert "name" in data
            print(f"✓ Root endpoint accessible")

    @pytest.mark.asyncio
    async def test_03_conversations_endpoint(self):
        """测试会话列表接口"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/conversations")
            assert response.status_code in [200, 401]
            print(f"✓ Conversations endpoint accessible")

    @pytest.mark.asyncio
    async def test_04_messages_endpoint(self):
        """测试消息接口"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/api/messages/test-conv-001")
            assert response.status_code in [200, 404]
            print(f"✓ Messages endpoint accessible")


class TestPhase2CoreComponents:
    """Phase 2: 核心组件集成测试"""

    @pytest.mark.asyncio
    async def test_05_query_engine_init(self):
        """测试QueryEngine初始化"""
        from app.core.query_engine import QueryEngine

        engine = QueryEngine()
        assert engine is not None
        print(f"✓ QueryEngine initialized")

    @pytest.mark.asyncio
    async def test_06_intent_classifier(self):
        """测试意图分类器"""
        from app.core.intent import IntentClassifier

        classifier = IntentClassifier()
        result = classifier.classify(TEST_REQUEST)
        print(f"✓ Intent classified: {result}")

    @pytest.mark.asyncio
    async def test_07_slot_extractor(self):
        """测试槽位提取器"""
        from app.core.intent import SlotExtractor

        extractor = SlotExtractor()
        slots = extractor.extract(TEST_REQUEST)
        print(f"✓ Slots extracted: {slots}")

    @pytest.mark.asyncio
    async def test_08_complexity_analyzer(self):
        """测试复杂度分析器"""
        from app.core.intent.complexity import is_complex_query

        result = is_complex_query(TEST_REQUEST)
        print(f"✓ Complexity analyzed: is_complex={result.is_complex}, score={result.score:.2f}")

    @pytest.mark.asyncio
    async def test_09_tool_registry(self):
        """测试工具注册表"""
        from app.core.tools.registry import global_registry

        tools = global_registry.list_tools()
        print(f"✓ Tool registry: {len(tools)} tools")

    @pytest.mark.asyncio
    async def test_10_token_budget_manager(self):
        """测试Token预算管理器"""
        from app.core.token_budget import get_token_budget_manager

        manager = get_token_budget_manager()
        assert manager is not None
        print(f"✓ TokenBudgetManager initialized")

    @pytest.mark.asyncio
    async def test_11_injection_guard(self):
        """测试注入防护"""
        from app.core.security.injection_guard import InjectionGuard

        guard = InjectionGuard()
        result = guard.check("我想去北京旅游")
        print(f"✓ InjectionGuard: decision={result.value}")

    @pytest.mark.asyncio
    async def test_12_security_auditor(self):
        """测试安全审计器"""
        from app.core.security.auditor import get_security_auditor

        auditor = get_security_auditor()
        assert auditor is not None
        print(f"✓ SecurityAuditor initialized")

    @pytest.mark.asyncio
    async def test_13_circuit_breaker(self):
        """测试熔断器"""
        from app.core.subagent.circuit_breaker import get_circuit_breaker_registry

        registry = get_circuit_breaker_registry()
        breaker = registry.get_breaker("TEST")
        assert breaker is not None
        print(f"✓ CircuitBreaker initialized")

    @pytest.mark.asyncio
    async def test_14_subagent_orchestrator(self):
        """测试子Agent协调器"""
        from app.core.subagent.orchestrator import SubAgentOrchestrator

        orchestrator = SubAgentOrchestrator()
        assert orchestrator is not None
        print(f"✓ SubAgentOrchestrator initialized")


class TestPhase2FixedFeatures:
    """Phase 2: 验证修复后的功能"""

    @pytest.mark.asyncio
    async def test_15_canary_controller(self):
        """测试灰度控制器"""
        from app.core.canary import get_canary_controller

        controller = get_canary_controller()
        result = controller.decide_version("test-user-123")
        print(f"✓ CanaryController: version={result.version}")

    @pytest.mark.asyncio
    async def test_16_rollback_manager(self):
        """测试回滚管理器"""
        from app.core.rollback import get_rollback_manager

        manager = get_rollback_manager()
        assert manager is not None
        print(f"✓ RollbackManager initialized")

    @pytest.mark.asyncio
    async def test_17_tracer(self):
        """测试追踪器"""
        from app.core.tracing import get_tracer

        tracer = get_tracer()
        assert tracer is not None
        print(f"✓ Tracer initialized")

    @pytest.mark.asyncio
    async def test_18_session_snapshot(self):
        """测试会话快照"""
        from app.core.session_snapshot import get_snapshot_manager

        manager = get_snapshot_manager()
        assert manager is not None
        print(f"✓ SessionSnapshotManager initialized")


class TestPhase2Integration:
    """Phase 2: 集成测试"""

    @pytest.mark.asyncio
    async def test_19_full_import_chain(self):
        """测试完整导入链"""
        # 验证所有核心模块可以正常导入
        modules = [
            "app.core.query_engine",
            "app.core.canary",
            "app.core.rollback",
            "app.core.tracing",
            "app.core.token_budget",
            "app.core.session_snapshot",
            "app.core.security.injection_guard",
            "app.core.security.auditor",
            "app.core.subagent.circuit_breaker",
            "app.core.subagent.orchestrator",
            "app.core.intent",
            "app.core.context_mgmt.manager",
            "app.core.memory.hierarchy",
        ]

        for mod in modules:
            try:
                __import__(mod)
                print(f"✓ Import OK: {mod}")
            except Exception as e:
                print(f"✗ Import FAILED: {mod} - {e}")
                raise

    @pytest.mark.asyncio
    async def test_20_no_regression_in_fixes(self):
        """验证修复未引入回归"""
        # 测试核心功能仍正常工作
        from app.core.canary import CanaryController
        from app.core.rollback import RollbackManager
        from app.core.tracing import Tracer
        from app.core.token_budget import TokenBudgetManager

        # CanaryController
        c = CanaryController()
        c.add_version('v1.0', traffic_ratio=0.5)
        result = c.decide_version('test-user')
        assert result.version in ['stable', 'v1.0']

        # RollbackManager
        r = RollbackManager()
        snapshot = await r.create_snapshot('v1.0', description='test')
        assert snapshot.version == 'v1.0'

        # Tracer
        t = Tracer()
        with t.start_span('test'):
            trace_id = t.get_current_trace_id()
        assert len(trace_id) == 16

        # TokenBudgetManager
        tb = TokenBudgetManager()
        result = await tb.check_budget('test', 1000)
        assert result.action.value in ['allow', 'warn', 'compress', 'reject']

        print(f"✓ No regression detected in fixed features")


class TestPhase2EightStepVerification:
    """Phase 2: 8步流程验证"""

    @pytest.mark.asyncio
    async def test_21_step_verification(self):
        """验证8步流程组件可用"""
        from app.core.query_engine import WorkflowStage

        # 验证所有8个阶段定义正确
        stages = [
            WorkflowStage.STAGE_0_INIT,
            WorkflowStage.STAGE_1_INTENT,
            WorkflowStage.STAGE_2_STORAGE,
            WorkflowStage.STAGE_3_CTX_CLEAN,
            WorkflowStage.STAGE_4_TOOLS,
            WorkflowStage.STAGE_5_CONTEXT,
            WorkflowStage.STAGE_6_LLM,
            WorkflowStage.STAGE_7_CTX_MANAGE,
            WorkflowStage.STAGE_8_MEMORY,
        ]

        for stage in stages:
            assert stage.value.startswith(str(stages.index(stage)))
            print(f"✓ Stage {stages.index(stage)}: {stage.value}")


if __name__ == '__main__':
    print("=" * 60)
    print("AI旅行助手 - Phase 2: 全链路核心功能冒烟回归")
    print("=" * 60)
    print(f"开始时间: {datetime.now().isoformat()}")
    print()

    exit_code = pytest.main([__file__, '-v', '--tb=short'])

    print()
    print("=" * 60)
    print(f"测试结束 - Exit Code: {exit_code}")
    print("=" * 60)

    sys.exit(exit_code)
