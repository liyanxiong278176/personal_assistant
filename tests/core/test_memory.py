"""测试记忆���级管理"""

import pytest
from datetime import datetime
from uuid import uuid4

from app.core.memory import (
    MemoryHierarchy,
    MemoryHierarchyFactory,
    MemoryInjector,
    MemoryItem,
    MemoryLevel,
    MemoryPromoter,
    MemoryType,
    PromotionResult,
    WorkingMemoryEntry,
)


class TestMemoryLevel:
    """测试记忆��级枚举"""

    def test_level_values(self):
        """测试层级值"""
        assert MemoryLevel.WORKING.value == "working"
        assert MemoryLevel.EPISODIC.value == "episodic"
        assert MemoryLevel.SEMANTIC.value == "semantic"

    def test_level_from_string(self):
        """测试从字符串创建层级"""
        level = MemoryLevel("working")
        assert level == MemoryLevel.WORKING


class TestMemoryType:
    """测试记忆类型枚举"""

    def test_type_values(self):
        """测试类型值"""
        assert MemoryType.FACT.value == "fact"
        assert MemoryType.PREFERENCE.value == "preference"
        assert MemoryType.INTENT.value == "intent"
        assert MemoryType.CONSTRAINT.value == "constraint"
        assert MemoryType.EMOTION.value == "emotion"
        assert MemoryType.STATE.value == "state"


class TestMemoryItem:
    """测试记忆项"""

    def test_basic_memory_item(self):
        """测试基本记忆项创建"""
        item = MemoryItem(
            content="用户想去北京旅游",
            level=MemoryLevel.EPISODIC,
        )
        assert item.content == "用户想去北京旅游"
        assert item.level == MemoryLevel.EPISODIC
        assert item.memory_type is None
        assert item.confidence == 0.5
        assert item.importance == 0.5
        assert isinstance(item.item_id, str)
        assert isinstance(item.created_at, datetime)

    def test_memory_item_with_type(self):
        """测试带类型的记忆项"""
        item = MemoryItem(
            content="用户喜欢自然景���",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE,
            confidence=0.9,
            importance=0.8,
        )
        assert item.memory_type == MemoryType.PREFERENCE
        assert item.confidence == 0.9
        assert item.importance == 0.8

    def test_memory_item_with_metadata(self):
        """测试带元数据的记忆项"""
        metadata = {"destination": "北京", "dates": ["2024-05-01", "2024-05-05"]}
        item = MemoryItem(
            content="用户计划五一去北京旅游5天",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.FACT,
            metadata=metadata,
        )
        assert item.metadata == metadata
        assert item.metadata["destination"] == "北京"

    def test_to_dict(self):
        """测试转换为字典"""
        item = MemoryItem(
            content="测试内容",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.FACT,
            confidence=0.8,
        )
        data = item.to_dict()
        assert data["content"] == "测试内容"
        assert data["level"] == "episodic"
        assert data["memory_type"] == "fact"
        assert data["confidence"] == 0.8
        assert "id" in data
        assert "created_at" in data

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "content": "测试内容",
            "level": "episodic",
            "memory_type": "fact",
            "metadata": {},
            "confidence": 0.8,
            "importance": 0.7,
        }
        item = MemoryItem.from_dict(data)
        assert item.content == "测试内容"
        assert item.level == MemoryLevel.EPISODIC
        assert item.memory_type == MemoryType.FACT
        assert item.confidence == 0.8


class TestWorkingMemoryEntry:
    """测试工作记忆条目"""

    def test_basic_entry(self):
        """测试基本条目创建"""
        entry = WorkingMemoryEntry(
            role="user",
            content="你好",
        )
        assert entry.role == "user"
        assert entry.content == "你好"
        assert entry.tokens == 0
        assert isinstance(entry.timestamp, datetime)

    def test_entry_with_tokens(self):
        """测试带token计数的条目"""
        entry = WorkingMemoryEntry(
            role="assistant",
            content="你好！有什么可以帮助你的吗？",
            tokens=15,
        )
        assert entry.tokens == 15

    def test_to_dict(self):
        """测试转换为字典"""
        entry = WorkingMemoryEntry(
            role="user",
            content="测试消息",
            tokens=10,
        )
        data = entry.to_dict()
        assert data["role"] == "user"
        assert data["content"] == "测试消息"
        assert data["tokens"] == 10
        assert "timestamp" in data


class TestMemoryHierarchy:
    """测试记忆层级管理器"""

    def test_basic_hierarchy(self):
        """测试基本层级创建"""
        hierarchy = MemoryHierarchy()
        assert hierarchy.get_working_token_count() == 0
        assert len(hierarchy.get_working()) == 0

    def test_hierarchy_with_ids(self):
        """测试带ID的层级创建"""
        conversation_id = uuid4()
        user_id = "user123"
        hierarchy = MemoryHierarchy(
            conversation_id=conversation_id,
            user_id=user_id,
        )
        assert hierarchy.conversation_id == conversation_id
        assert hierarchy.user_id == user_id

    def test_add_working_message(self):
        """测试添加工作记忆消息"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_working_message("user", "你好")
        hierarchy.add_working_message("assistant", "你好！")

        working = hierarchy.get_working()
        assert len(working) == 2
        assert working[0]["role"] == "user"
        assert working[0]["content"] == "你好"
        assert working[1]["role"] == "assistant"

    def test_working_token_count(self):
        """测试工作记忆token计数"""
        hierarchy = MemoryHierarchy(working_max_tokens=100)
        hierarchy.add_working_message("user", "测试消息", tokens=20)
        hierarchy.add_working_message("assistant", "回复消息", tokens=15)

        assert hierarchy.get_working_token_count() == 35

    def test_working_token_limit_trim(self):
        """测试工作记忆token限制裁剪"""
        hierarchy = MemoryHierarchy(working_max_size=100, working_max_tokens=50)

        # Add messages that exceed token limit
        hierarchy.add_working_message("user", "消息1", tokens=20)
        hierarchy.add_working_message("assistant", "回复1", tokens=20)
        hierarchy.add_working_message("user", "消息2", tokens=20)

        # Should trim to stay within limit
        assert hierarchy.get_working_token_count() <= 50
        # Oldest messages should be removed
        working = hierarchy.get_working()
        assert len(working) >= 2  # At least 2 messages remain

    def test_get_working_limit(self):
        """测试获取工作记忆限制"""
        hierarchy = MemoryHierarchy()
        for i in range(20):
            hierarchy.add_working_message("user", f"消息{i}")

        working = hierarchy.get_working(limit=5)
        assert len(working) == 5
        # Should get the most recent 5
        assert "消息19" in working[-1]["content"]

    def test_add_episodic(self):
        """测试添加情景记忆"""
        hierarchy = MemoryHierarchy()
        item = MemoryItem(
            content="用户想去北京",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.INTENT,
        )
        hierarchy.add_episodic(item)

        episodic = hierarchy.get_episodic()
        assert len(episodic) == 1
        assert episodic[0].content == "用户想去北京"
        assert episodic[0].memory_type == MemoryType.INTENT

    def test_add_episodic_auto_level(self):
        """测试情景记忆自动设置层级"""
        hierarchy = MemoryHierarchy()
        item = MemoryItem(
            content="测试",
            level=MemoryLevel.WORKING,  # Wrong level
        )
        hierarchy.add_episodic(item)

        episodic = hierarchy.get_episodic()
        assert episodic[0].level == MemoryLevel.EPISODIC

    def test_get_episodic_with_type_filter(self):
        """测试按类型过滤情景记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_episodic(MemoryItem(
            content="偏好1", level=MemoryLevel.EPISODIC, memory_type=MemoryType.PREFERENCE
        ))
        hierarchy.add_episodic(MemoryItem(
            content="事实1", level=MemoryLevel.EPISODIC, memory_type=MemoryType.FACT
        ))
        hierarchy.add_episodic(MemoryItem(
            content="偏好2", level=MemoryLevel.EPISODIC, memory_type=MemoryType.PREFERENCE
        ))

        preferences = hierarchy.get_episodic(memory_type=MemoryType.PREFERENCE)
        assert len(preferences) == 2
        assert all(m.memory_type == MemoryType.PREFERENCE for m in preferences)

    def test_get_episodic_with_importance_filter(self):
        """测试按重要性过滤情景记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_episodic(MemoryItem(
            content="重要", level=MemoryLevel.EPISODIC, importance=0.9
        ))
        hierarchy.add_episodic(MemoryItem(
            content="一般", level=MemoryLevel.EPISODIC, importance=0.5
        ))
        hierarchy.add_episodic(MemoryItem(
            content="次要", level=MemoryLevel.EPISODIC, importance=0.3
        ))

        important = hierarchy.get_episodic(min_importance=0.7)
        assert len(important) == 1
        assert important[0].content == "重要"

    def test_get_episodic_sorting(self):
        """测试情景记忆排序"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_episodic(MemoryItem(
            content="低重要性", level=MemoryLevel.EPISODIC, importance=0.3
        ))
        hierarchy.add_episodic(MemoryItem(
            content="高重要性", level=MemoryLevel.EPISODIC, importance=0.9
        ))
        hierarchy.add_episodic(MemoryItem(
            content="中重要性", level=MemoryLevel.EPISODIC, importance=0.6
        ))

        episodic = hierarchy.get_episodic()
        # Should be sorted by importance descending
        assert episodic[0].importance >= episodic[1].importance
        assert episodic[1].importance >= episodic[2].importance

    def test_add_semantic(self):
        """测试添加语义记忆"""
        hierarchy = MemoryHierarchy()
        item = MemoryItem(
            content="用户喜欢自然景观",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE,
        )
        hierarchy.add_semantic(item)

        semantic = hierarchy.get_semantic()
        assert len(semantic) == 1
        assert semantic[0].content == "用户喜欢自然景观"

    def test_get_semantic_with_query(self):
        """测试带查询的语义记忆获取"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
        ))
        hierarchy.add_semantic(MemoryItem(
            content="用户预算充足",
            level=MemoryLevel.SEMANTIC,
        ))

        results = hierarchy.get_semantic(query="北京")
        assert len(results) == 1
        assert "北京" in results[0].content

    def test_get_semantic_with_type_filter(self):
        """测试按类型过滤语义记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_semantic(MemoryItem(
            content="偏好1", level=MemoryLevel.SEMANTIC, memory_type=MemoryType.PREFERENCE
        ))
        hierarchy.add_semantic(MemoryItem(
            content="事实1", level=MemoryLevel.SEMANTIC, memory_type=MemoryType.FACT
        ))

        preferences = hierarchy.get_semantic(memory_type=MemoryType.PREFERENCE)
        assert len(preferences) == 1
        assert preferences[0].memory_type == MemoryType.PREFERENCE

    def test_add_method_routing(self):
        """测试add方法路由"""
        hierarchy = MemoryHierarchy()

        # Test working level
        working_item = MemoryItem(
            content="工作消息",
            level=MemoryLevel.WORKING,
        )
        hierarchy.add(working_item)
        assert len(hierarchy.get_working()) == 1

        # Test episodic level
        episodic_item = MemoryItem(
            content="情景记忆",
            level=MemoryLevel.EPISODIC,
        )
        hierarchy.add(episodic_item)
        assert len(hierarchy.get_episodic()) == 1

        # Test semantic level
        semantic_item = MemoryItem(
            content="语义记忆",
            level=MemoryLevel.SEMANTIC,
        )
        hierarchy.add(semantic_item)
        assert len(hierarchy.get_semantic()) == 1

    def test_clear_working(self):
        """测试清除工作记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_working_message("user", "测试")
        assert len(hierarchy.get_working()) == 1

        hierarchy.clear_working()
        assert len(hierarchy.get_working()) == 0
        assert hierarchy.get_working_token_count() == 0

    def test_clear_episodic(self):
        """测试清除情景记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_episodic(MemoryItem(
            content="测试", level=MemoryLevel.EPISODIC
        ))
        assert len(hierarchy.get_episodic()) == 1

        hierarchy.clear_episodic()
        assert len(hierarchy.get_episodic()) == 0

    def test_clear_semantic(self):
        """测试清除语义记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_semantic(MemoryItem(
            content="测试", level=MemoryLevel.SEMANTIC
        ))
        assert len(hierarchy.get_semantic()) == 1

        hierarchy.clear_semantic()
        assert len(hierarchy.get_semantic()) == 0

    def test_clear_all(self):
        """测试清除所有记忆"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_working_message("user", "测试")
        hierarchy.add_episodic(MemoryItem(
            content="测试", level=MemoryLevel.EPISODIC
        ))
        hierarchy.add_semantic(MemoryItem(
            content="测试", level=MemoryLevel.SEMANTIC
        ))

        hierarchy.clear_all()
        assert len(hierarchy.get_working()) == 0
        assert len(hierarchy.get_episodic()) == 0
        assert len(hierarchy.get_semantic()) == 0

    def test_promote_to_semantic_success(self):
        """测试成功晋升到语义记忆"""
        hierarchy = MemoryHierarchy()
        item = MemoryItem(
            content="重要偏好",
            level=MemoryLevel.EPISODIC,
            importance=0.8,
        )

        result = hierarchy.promote_to_semantic(item, min_importance=0.7)
        assert result is True
        assert item.level == MemoryLevel.SEMANTIC
        assert len(hierarchy.get_semantic()) == 1

    def test_promote_to_semantic_failure(self):
        """测试晋升失败（重要性不足）"""
        hierarchy = MemoryHierarchy()
        item = MemoryItem(
            content="不重要",
            level=MemoryLevel.EPISODIC,
            importance=0.5,
        )

        result = hierarchy.promote_to_semantic(item, min_importance=0.7)
        assert result is False
        assert item.level == MemoryLevel.EPISODIC  # Level unchanged
        assert len(hierarchy.get_semantic()) == 0

    def test_get_context_summary(self):
        """测试获取上下文摘要"""
        conversation_id = uuid4()
        hierarchy = MemoryHierarchy(
            conversation_id=conversation_id,
            user_id="user123",
        )
        hierarchy.add_working_message("user", "测试", tokens=10)
        hierarchy.add_episodic(MemoryItem(
            content="测试", level=MemoryLevel.EPISODIC
        ))
        hierarchy.add_semantic(MemoryItem(
            content="测试", level=MemoryLevel.SEMANTIC
        ))

        summary = hierarchy.get_context_summary()
        assert summary["working_count"] == 1
        assert summary["working_tokens"] == 10
        assert summary["episodic_count"] == 1
        assert summary["semantic_count"] == 1
        assert str(conversation_id) in summary["conversation_id"]
        assert summary["user_id"] == "user123"

    def test_to_llm_context(self):
        """测试转换为LLM上下文"""
        hierarchy = MemoryHierarchy()
        hierarchy.add_working_message("user", "你好")
        hierarchy.add_working_message("assistant", "你好！")

        context = hierarchy.to_llm_context()
        assert len(context) == 2
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "你好"
        assert context[1]["role"] == "assistant"

    def test_estimate_tokens(self):
        """测试token估算"""
        # Chinese text: approximately 1 token per 4 characters
        chinese_text = "这是一段中文文本用于测试token估算功能"
        estimated = MemoryHierarchy._estimate_tokens(chinese_text)
        assert estimated > 0
        # Rough check: should be around (length / 4) + 10
        expected = len(chinese_text) // 4 + 10
        assert estimated == expected


class TestMemoryHierarchyFactory:
    """测试记忆层级工厂"""

    @pytest.mark.asyncio
    async def test_factory_creation(self):
        """测试工厂创建"""
        factory = MemoryHierarchyFactory()
        assert factory._episodic_backend is None
        assert factory._semantic_backend is None

    @pytest.mark.asyncio
    async def test_load_conversation_context_no_backends(self):
        """测试无后端时加载对话上下文"""
        factory = MemoryHierarchyFactory()
        conversation_id = uuid4()
        user_id = "user123"

        hierarchy = await factory.load_conversation_context(conversation_id, user_id)
        assert isinstance(hierarchy, MemoryHierarchy)
        assert hierarchy.conversation_id == conversation_id
        assert hierarchy.user_id == user_id
        assert len(hierarchy.get_episodic()) == 0
        assert len(hierarchy.get_semantic()) == 0

    @pytest.mark.asyncio
    async def test_load_conversation_context_with_backends(self):
        """测试带后端时加载对话上下文"""
        async def mock_episodic_backend(conv_id):
            return [
                {
                    "content": "情景记忆1",
                    "level": "episodic",
                    "memory_type": "fact",
                    "metadata": {},
                }
            ]

        async def mock_semantic_backend(user_id):
            return [
                {
                    "content": "语义记忆1",
                    "level": "semantic",
                    "memory_type": "preference",
                    "metadata": {},
                }
            ]

        factory = MemoryHierarchyFactory(
            episodic_backend=mock_episodic_backend,
            semantic_backend=mock_semantic_backend,
        )

        hierarchy = await factory.load_conversation_context(uuid4(), "user123")
        assert len(hierarchy.get_episodic()) == 1
        assert len(hierarchy.get_semantic()) == 1
        assert hierarchy.get_episodic()[0].content == "情景记忆1"
        assert hierarchy.get_semantic()[0].content == "语义记忆1"

    @pytest.mark.asyncio
    async def test_persist_episodic_no_backend(self):
        """测试无后端时持久化情景记忆"""
        factory = MemoryHierarchyFactory()
        item = MemoryItem(content="测试", level=MemoryLevel.EPISODIC)

        result = await factory.persist_episodic(uuid4(), item)
        assert result is False

    @pytest.mark.asyncio
    async def test_persist_semantic_no_backend(self):
        """测试无后端时持久化语义记忆"""
        factory = MemoryHierarchyFactory()
        item = MemoryItem(content="测试", level=MemoryLevel.SEMANTIC)

        result = await factory.persist_semantic("user123", item)
        assert result is False

    @pytest.mark.asyncio
    async def test_persist_episodic_with_backend(self):
        """测试带后端时持久化情景记忆"""
        async def mock_backend(conv_id, data):
            return True

        factory = MemoryHierarchyFactory(episodic_backend=mock_backend)
        item = MemoryItem(content="测试", level=MemoryLevel.EPISODIC)

        result = await factory.persist_episodic(uuid4(), item)
        assert result is True

    @pytest.mark.asyncio
    async def test_persist_semantic_with_backend(self):
        """测试带后端时持久化语义记忆"""
        async def mock_backend(user_id, data):
            return True

        factory = MemoryHierarchyFactory(semantic_backend=mock_backend)
        item = MemoryItem(content="测试", level=MemoryLevel.SEMANTIC)

        result = await factory.persist_semantic("user123", item)
        assert result is True

    @pytest.mark.asyncio
    async def test_backend_error_handling(self):
        """测试后端错误处理"""
        async def failing_backend(*args):
            raise Exception("Backend error")

        factory = MemoryHierarchyFactory(
            episodic_backend=failing_backend,
            semantic_backend=failing_backend,
        )

        # Should not raise, just log error
        hierarchy = await factory.load_conversation_context(uuid4(), "user123")
        assert isinstance(hierarchy, MemoryHierarchy)

        item = MemoryItem(content="测试", level=MemoryLevel.EPISODIC)
        result = await factory.persist_episodic(uuid4(), item)
        assert result is False


class TestMemoryInjector:
    """测试自动记忆注入器"""

    def test_injector_creation(self):
        """测试注入器创建"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)
        assert injector._hierarchy == hierarchy

    def test_extract_keywords_chinese(self):
        """测试中文关键词提取"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("我想去北京旅游")
        assert "北京" in keywords
        assert "旅游" in keywords
        # Stopwords should be filtered
        assert "我" not in keywords
        assert "想" not in keywords
        assert "去" not in keywords

    def test_extract_keywords_english(self):
        """测试英文关键词提取"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("I want to visit Beijing for travel")
        assert "want" in keywords
        assert "visit" in keywords
        assert "beijing" in keywords
        assert "travel" in keywords
        # Stopwords should be filtered
        assert "i" not in keywords
        assert "to" not in keywords
        assert "for" not in keywords

    def test_extract_keywords_mixed(self):
        """测试中英文混合关键词提取"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("我想去 Beijing 旅游，预算 5000 元")
        assert "北京" not in keywords  # Chinese "北京" not in input
        assert "beijing" in keywords
        assert "旅游" in keywords
        assert "5000" in keywords

    def test_extract_keywords_numbers(self):
        """测试数字提取"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("我的预算是5000元，计划5天行程")
        assert "5000" in keywords
        assert "5" in keywords

    def test_extract_keywords_empty(self):
        """测试空字符串关键词提取"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("")
        assert keywords == []

    def test_extract_keywords_deduplication(self):
        """测试关键词去重"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("北京北京旅游旅游")
        assert keywords.count("北京") == 1
        assert keywords.count("旅游") == 1

    def test_extract_keywords_min_length(self):
        """测试最小长度过滤"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("我想去北京")
        # Single character Chinese words should be filtered
        assert "我" not in keywords
        assert "想" not in keywords
        assert "去" not in keywords
        # But 2+ character words should be included
        assert "北京" in keywords

    def test_get_relevant_memories_empty(self):
        """测试空语义记忆检索"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        memories = injector.get_relevant_memories("我想去北京旅游")
        assert memories == []

    def test_get_relevant_memories_basic(self):
        """测试基本相关记忆检索"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        # Add semantic memories
        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,
        ))
        hierarchy.add_semantic(MemoryItem(
            content="用户预算充足",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.FACT,
            importance=0.7,
        ))

        memories = injector.get_relevant_memories("我想去北京旅游")
        assert len(memories) > 0
        assert any("北京" in m for m in memories)

    def test_get_relevant_memories_max_limit(self):
        """测试记忆数量限制"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        # Add multiple semantic memories
        for i in range(5):
            hierarchy.add_semantic(MemoryItem(
                content=f"用户偏好{i}：喜欢旅游",
                level=MemoryLevel.SEMANTIC,
                importance=0.5,
            ))

        memories = injector.get_relevant_memories("旅游", max_memories=3)
        assert len(memories) <= 3

    def test_get_relevant_memories_min_importance(self):
        """测试最小重要性过滤"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢旅游",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))
        hierarchy.add_semantic(MemoryItem(
            content="次要信息",
            level=MemoryLevel.SEMANTIC,
            importance=0.2,
        ))

        memories = injector.get_relevant_memories("旅游", min_importance=0.5)
        assert len(memories) == 1
        assert "喜欢旅游" in memories[0]

    def test_get_relevant_memories_keyword_matching(self):
        """测试关键词匹配"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢上海的城市风光",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))
        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))

        memories = injector.get_relevant_memories("我想去北京")
        assert len(memories) >= 1
        assert any("北京" in m for m in memories)
        # Shanghai should not be in results (less relevant)
        assert not any("上海" in m for m in memories)

    def test_get_relevant_memories_metadata_matching(self):
        """测试元数据匹配"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户旅游偏好",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
            metadata={"destination": "北京", "budget": 5000},
        ))

        memories = injector.get_relevant_memories("我想去北京旅游")
        assert len(memories) > 0

    def test_build_memory_context_empty(self):
        """测试空记忆上下文构建"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        context = injector.build_memory_context("我想去北京旅游")
        assert context == ""

    def test_build_memory_context_with_memories(self):
        """测试带记忆的上下文构建"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))

        context = injector.build_memory_context("我想去北京旅游")
        assert "用户偏好记忆" in context
        assert "用户喜欢北京的自然景观" in context
        assert "1." in context  # Should have numbered list

    def test_build_memory_context_include_empty(self):
        """测试包含空消息的上下文构建"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        context = injector.build_memory_context(
            "我想去北京旅游",
            include_empty=True
        )
        assert "用户偏好记忆" in context
        assert "暂无相关记忆" in context

    def test_build_memory_context_multiple_memories(self):
        """测试多条记忆的上下文构建"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))
        hierarchy.add_semantic(MemoryItem(
            content="用户预算充足",
            level=MemoryLevel.SEMANTIC,
            importance=0.7,
        ))

        context = injector.build_memory_context("我想去北京旅游", max_memories=5)
        lines = context.split("\n")
        # Should have header + 2 memory lines
        assert len([l for l in lines if l.strip()]) >= 3

    def test_build_memory_context_max_limit(self):
        """测试上下文构建的数量限制"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        for i in range(5):
            hierarchy.add_semantic(MemoryItem(
                content=f"用户偏好{i}：旅游",
                level=MemoryLevel.SEMANTIC,
                importance=0.5,
            ))

        context = injector.build_memory_context("旅游", max_memories=2)
        # Should only include 2 memories
        assert context.count("用户偏好") <= 2

    def test_get_memory_injection_prompt(self):
        """测试获取记忆注入提示词"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))

        prompt = injector.get_memory_injection_prompt("我想去北京旅游")
        assert "用户偏好记忆" in prompt
        assert "用户喜欢北京的自然景观" in prompt
        assert "我想去北京旅游" in prompt

    def test_get_memory_injection_prompt_no_memories(self):
        """测试无记忆时的注入提示词"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        prompt = injector.get_memory_injection_prompt("我想去北京旅游")
        # Should only have user input
        assert prompt == "用户输入：我想去北京旅游"

    def test_find_memories_by_type(self):
        """测试按类型查找记忆"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        hierarchy.add_semantic(MemoryItem(
            content="用户喜欢自然景观",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,
        ))
        hierarchy.add_semantic(MemoryItem(
            content="用户预算是5000元",
            level=MemoryLevel.SEMANTIC,
            memory_type=MemoryType.FACT,
            importance=0.7,
        ))

        memories = injector.find_memories_by_type(
            "用户喜欢什么",
            memory_type="preference"
        )
        assert len(memories) >= 1
        assert any("自然景观" in m for m in memories)
        assert not any("预算" in m for m in memories)

    def test_find_memories_by_type_invalid(self):
        """测试无效类型查找"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        memories = injector.find_memories_by_type(
            "测试",
            memory_type="invalid_type"
        )
        assert memories == []

    def test_relevance_score_calculation(self):
        """测试相关性分数计算"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        memory = MemoryItem(
            content="用户喜欢北京的自然景观",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        )

        # High relevance - keyword matches
        score = injector._calculate_relevance_score(memory, ["北京", "旅游"])
        assert score > 0

        # Low relevance - no matches
        score = injector._calculate_relevance_score(memory, ["上海", "美食"])
        assert score == 0

    def test_relevance_score_importance_weight(self):
        """测试重要性权重对分数的影响"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        high_importance = MemoryItem(
            content="用户喜欢北京",
            level=MemoryLevel.SEMANTIC,
            importance=0.9,
        )
        low_importance = MemoryItem(
            content="用户喜欢北京",
            level=MemoryLevel.SEMANTIC,
            importance=0.3,
        )

        high_score = injector._calculate_relevance_score(high_importance, ["北京"])
        low_score = injector._calculate_relevance_score(low_importance, ["北京"])

        assert high_score > low_score

    def test_chinese_stopwords_filtering(self):
        """测试中文停用词过滤"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("我和我的朋友想去北京旅游")
        assert "我" not in keywords
        assert "的" not in keywords
        assert "想" not in keywords
        assert "去" not in keywords
        assert "北京" in keywords
        assert "旅游" in keywords

    def test_english_stopwords_filtering(self):
        """测试英文停用词过滤"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords("The user wants to visit Beijing")
        assert "the" not in keywords
        assert "to" not in keywords
        assert "user" in keywords or "wants" in keywords
        assert "visit" in keywords
        assert "beijing" in keywords

    def test_complex_sentence_keyword_extraction(self):
        """测试复杂句子的关键词提取"""
        hierarchy = MemoryHierarchy()
        injector = MemoryInjector(hierarchy)

        keywords = injector.extract_keywords(
            "请问能不能帮我推荐一下北京周边有哪些不错的自然景观适合五一假期去游玩的？"
        )
        # Should extract meaningful keywords
        assert "北京" in keywords
        assert "自然景观" in keywords
        assert "五一" in keywords
        # Should filter stopwords
        assert "请问" not in keywords
        assert "能不能" not in keywords
        assert "一下" not in keywords


class TestMemoryPromoter:
    """测试记忆晋升器"""

    def test_promoter_creation(self):
        """测试晋升器创建"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)
        assert promoter._hierarchy == hierarchy
        assert promoter._importance_threshold == 0.7

    def test_promoter_custom_threshold(self):
        """测试自定义重要性阈值"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.5)
        assert promoter._importance_threshold == 0.5

    def test_is_preference_chinese(self):
        """测试中文偏好识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        assert promoter._is_preference("我喜欢自然景观") is True
        assert promoter._is_preference("我偏爱安静的景点") is True
        assert promoter._is_preference("今天天气怎么样") is False

    def test_is_preference_english(self):
        """测试英文偏好识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        assert promoter._is_preference("I like nature scenes") is True
        assert promoter._is_preference("I prefer quiet places") is True
        assert promoter._is_preference("How is the weather") is False

    def test_is_fact_chinese(self):
        """测试中文事实识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        assert promoter._is_fact("我的预算是5000元") is True
        assert promoter._is_fact("计划5天行程") is True
        assert promoter._is_fact("我想去旅游") is False

    def test_is_fact_with_numbers(self):
        """测试带数字的事实识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        # Numbers should trigger fact detection
        assert promoter._is_fact("我有3个人") is True
        assert promoter._is_fact("预算5000") is True

    def test_is_constraint_chinese(self):
        """测试中文约束识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        assert promoter._is_constraint("不能超过5000元") is True
        assert promoter._is_constraint("避免热门景点") is True
        assert promoter._is_constraint("我想去旅游") is False

    def test_is_constraint_english(self):
        """测试英文约束识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        assert promoter._is_constraint("Cannot exceed 5000") is True
        assert promoter._is_constraint("Avoid crowded places") is True
        assert promoter._is_constraint("I want to travel") is False

    def test_determine_memory_type_preference(self):
        """测试偏好类型识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory_type = promoter._determine_memory_type("我喜欢自然景观")
        assert memory_type == MemoryType.PREFERENCE

    def test_determine_memory_type_constraint(self):
        """测试约束类型识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory_type = promoter._determine_memory_type("预算不能超过5000元")
        assert memory_type == MemoryType.CONSTRAINT

    def test_determine_memory_type_fact(self):
        """测试事实类型识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory_type = promoter._determine_memory_type("我有5000元预算")
        assert memory_type == MemoryType.FACT

    def test_determine_memory_type_default(self):
        """测试默认类型识别"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory_type = promoter._determine_memory_type("今天天气不错")
        assert memory_type == MemoryType.FACT  # Default

    def test_calculate_importance_from_content_length(self):
        """测试基于内容长度的重要性计算"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        # Short content
        short_score = promoter._calculate_importance_from_content("你好")
        # Long content
        long_score = promoter._calculate_importance_from_content("这是一段很长的内容包含了很多重要信息")

        assert long_score > short_score

    def test_calculate_importance_from_content_keywords(self):
        """测试基于关键词的重要性计算"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        # With preference keyword
        pref_score = promoter._calculate_importance_from_content("我喜欢自然景观")
        # Without keywords
        plain_score = promoter._calculate_importance_from_content("今天天气不错")

        assert pref_score > plain_score

    def test_calculate_importance_from_content_constraint(self):
        """测试约束内容的重要性计算"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        score = promoter._calculate_importance_from_content("预算不能超过5000元")
        assert score > 0.3  # Constraint keywords should boost score

    def test_calculate_importance_from_content_numbers(self):
        """测试带数字内容的重要性计算"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        # With large number
        score_with_number = promoter._calculate_importance_from_content("预算5000元")
        # Without number
        score_without = promoter._calculate_importance_from_content("预算充足")

        assert score_with_number > score_without

    def test_track_access(self):
        """测试访问追踪"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory_id = "test-memory-123"
        promoter.track_access(memory_id)
        promoter.track_access(memory_id)

        assert promoter.get_access_count(memory_id) == 2

    def test_get_access_count_nonexistent(self):
        """测试获取不存在记忆的访问计数"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        count = promoter.get_access_count("nonexistent")
        assert count == 0

    def test_reset_access_counts(self):
        """测试重置访问计数"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        promoter.track_access("memory1")
        promoter.track_access("memory2")
        promoter.reset_access_counts()

        assert promoter.get_access_count("memory1") == 0
        assert promoter.get_access_count("memory2") == 0

    @pytest.mark.asyncio
    async def test_promote_episodic_to_semantic_empty(self):
        """测试空情景记忆晋升"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        count = await promoter.promote_episodic_to_semantic("user123")
        assert count == 0

    @pytest.mark.asyncio
    async def test_promote_episodic_to_semantic_success(self):
        """测试成功晋升情景记忆"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.5)

        # Add episodic memory with high importance
        hierarchy.add_episodic(MemoryItem(
            content="我喜欢自然景观，预算5000元",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,
        ))

        count = await promoter.promote_episodic_to_semantic("user123")
        assert count == 1

        # Check semantic memory was added
        semantic = hierarchy.get_semantic()
        assert len(semantic) == 1
        assert semantic[0].level == MemoryLevel.SEMANTIC

    @pytest.mark.asyncio
    async def test_promote_episodic_to_semantic_below_threshold(self):
        """测试低于阈值的记忆不晋升"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.8)

        # Add episodic memory with low importance
        hierarchy.add_episodic(MemoryItem(
            content="不太重要的信息",
            level=MemoryLevel.EPISODIC,
            importance=0.5,
        ))

        count = await promoter.promote_episodic_to_semantic("user123")
        assert count == 0

        # Check semantic memory was NOT added
        semantic = hierarchy.get_semantic()
        assert len(semantic) == 0

    @pytest.mark.asyncio
    async def test_promote_episodic_to_semantic_mixed(self):
        """测试混合重要性记忆的晋升"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.6)

        # Add multiple episodic memories
        hierarchy.add_episodic(MemoryItem(
            content="重要的偏好信息",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,
        ))
        hierarchy.add_episodic(MemoryItem(
            content="中等重要信息",
            level=MemoryLevel.EPISODIC,
            importance=0.5,
        ))
        hierarchy.add_episodic(MemoryItem(
            content="另一个重要偏好",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.7,
        ))

        count = await promoter.promote_episodic_to_semantic("user123")
        # Should promote 2 (importance 0.8 and 0.7)
        assert count == 2

    @pytest.mark.asyncio
    async def test_promote_episodic_to_semantic_already_semantic(self):
        """测试已晋升的记忆不再晋升"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        # Add semantic memory directly
        hierarchy.add_semantic(MemoryItem(
            content="已存在的语义记忆",
            level=MemoryLevel.SEMANTIC,
            importance=0.8,
        ))

        count = await promoter.promote_episodic_to_semantic("user123")
        assert count == 0  # Should not promote already semantic memories

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_empty(self):
        """测试空对话的自动晋升"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            [],
            "user123"
        )

        assert result["extracted_count"] == 0
        assert result["promoted_count"] == 0
        assert result["memories"] == []

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_preference(self):
        """测试从对话中提取并晋升偏好"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.3)

        messages = [
            {"role": "user", "content": "我喜欢自然景观"},
            {"role": "assistant", "content": "好的"},
        ]

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            messages,
            "user123"
        )

        assert result["extracted_count"] == 1
        assert result["promoted_count"] == 1
        assert len(result["memories"]) == 1
        assert "喜欢" in result["memories"][0]

        # Check semantic memory was added
        semantic = hierarchy.get_semantic()
        assert len(semantic) == 1

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_only_user_messages(self):
        """测试只处理用户消息"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        messages = [
            {"role": "assistant", "content": "你好"},
            {"role": "user", "content": "我喜欢自然景观"},
            {"role": "assistant", "content": "好的"},
        ]

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            messages,
            "user123"
        )

        # Should only extract from user message
        assert result["extracted_count"] == 1

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_non_preference(self):
        """测试非偏好内容不提取"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        messages = [
            {"role": "user", "content": "你好"},
        ]

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            messages,
            "user123"
        )

        # Greeting should not be extracted
        assert result["extracted_count"] == 0

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_fact(self):
        """测试从对话中提取事实"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.4)

        messages = [
            {"role": "user", "content": "我的预算是5000元"},
        ]

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            messages,
            "user123"
        )

        assert result["extracted_count"] >= 1

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_constraint(self):
        """测试从对话中提取约束"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.4)

        messages = [
            {"role": "user", "content": "预算不能超过5000元"},
        ]

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            messages,
            "user123"
        )

        assert result["extracted_count"] >= 1
        # Should be marked as constraint type
        episodic = hierarchy.get_episodic()
        assert any(m.memory_type == MemoryType.CONSTRAINT for m in episodic)

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_below_threshold(self):
        """测试低于阈值的内容不晋升"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.9)

        messages = [
            {"role": "user", "content": "我喜欢旅游"},  # Low importance
        ]

        result = await promoter.auto_promote_from_conversation(
            uuid4(),
            messages,
            "user123"
        )

        # Extracted but not promoted
        assert result["extracted_count"] >= 1
        assert result["promoted_count"] == 0

    @pytest.mark.asyncio
    async def test_auto_promote_from_conversation_metadata(self):
        """测试晋升记忆包含元数据"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy, importance_threshold=0.3)

        conv_id = uuid4()
        messages = [
            {"role": "user", "content": "我喜欢自然景观"},
        ]

        await promoter.auto_promote_from_conversation(
            conv_id,
            messages,
            "user123"
        )

        # Check metadata includes conversation_id
        semantic = hierarchy.get_semantic()
        assert len(semantic) >= 1
        assert "conversation_id" in semantic[0].metadata

    def test_calculate_importance_with_memory(self):
        """测试完整记忆项的重要性计算"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory = MemoryItem(
            content="我喜欢自然景观",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.5,
            confidence=0.8,
        )

        importance = promoter._calculate_importance(memory)
        assert 0.0 <= importance <= 1.0
        # Should be higher than base importance due to preference type
        assert importance > 0.5

    def test_calculate_importance_with_access_count(self):
        """测试访问��数对重要性的影响"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        memory = MemoryItem(
            content="我喜欢旅游",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.5,
        )

        # Track some accesses
        promoter.track_access(memory.item_id)
        promoter.track_access(memory.item_id)

        importance = promoter._calculate_importance(memory)
        # Should be higher than base due to access count
        assert importance > 0.5

    def test_calculate_importance_constraint_bonus(self):
        """测试约束类型的重要性加成"""
        hierarchy = MemoryHierarchy()
        promoter = MemoryPromoter(hierarchy)

        constraint_memory = MemoryItem(
            content="预算限制",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.CONSTRAINT,
            importance=0.5,
        )

        fact_memory = MemoryItem(
            content="普通事实",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.FACT,
            importance=0.5,
        )

        constraint_importance = promoter._calculate_importance(constraint_memory)
        fact_importance = promoter._calculate_importance(fact_memory)

        # Constraint should have higher importance
        assert constraint_importance > fact_importance


class TestPromotionResult:
    """测试晋升结果类"""

    def test_default_values(self):
        """测试默认值"""
        result = PromotionResult()
        assert result.promoted_count == 0
        assert result.skipped_count == 0
        assert result.errors == []
        assert result.promoted_ids == []

    def test_with_values(self):
        """测试带参数创建"""
        result = PromotionResult(
            promoted_count=5,
            skipped_count=2,
            errors=["error1"],
            promoted_ids=["id1", "id2"],
        )
        assert result.promoted_count == 5
        assert result.skipped_count == 2
        assert result.errors == ["error1"]
        assert result.promoted_ids == ["id1", "id2"]

    def test_to_dict(self):
        """测试转换为���典"""
        result = PromotionResult(
            promoted_count=3,
            skipped_count=1,
        )
        data = result.to_dict()
        assert data["promoted_count"] == 3
        assert data["skipped_count"] == 1
        assert "errors" in data
        assert "promoted_ids" in data
