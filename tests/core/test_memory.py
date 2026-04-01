"""测试记忆���级管理"""

import pytest
from datetime import datetime
from uuid import uuid4

from app.core.memory import (
    MemoryHierarchy,
    MemoryHierarchyFactory,
    MemoryItem,
    MemoryLevel,
    MemoryType,
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
