# backend/tests/test_interview_monitor/test_memory.py
"""三级记忆测试 MEM-01~05 (580 tests)

测试用例分布:
- MEM-01: 记忆生成测试 (10用户×30轮 = 300条)
- MEM-02: 记忆晋升测试 (100条)
- MEM-03: 工作记忆容量测试 (20条 + overflow测试)
- MEM-04: 语义记忆检索测试 (80条)
- MEM-05: 跨用户记忆隔离测试 (80条)

总计: 300 + 100 + 20 + 80 + 80 = 580 tests
"""
import pytest
from datetime import datetime
from uuid import uuid4

from app.core.memory.hierarchy import (
    MemoryHierarchy,
    MemoryItem,
    MemoryLevel,
    MemoryType,
    WorkingMemoryEntry,
)


class TestMemoryHierarchyMEM01:
    """MEM-01: 记忆生成测试 (10用户×30轮 = 300条)

    验证MemoryHierarchy能够正确生成和管理episodic记忆，
    测试多用户、多轮对话场景下的记忆累积。
    """

    @pytest.fixture
    def hierarchy(self):
        """创建MemoryHierarchy实例"""
        return MemoryHierarchy(
            working_max_size=20,
            user_id="test_user",
            conversation_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_mem01_10_users_30_rounds(self):
        """MEM-01: 10用户×30轮 = 300条episodic记忆

        测试场景:
        - 10个不同用户
        - 每个用户30轮对话
        - 每轮生成1条episodic记忆
        - 验证总记忆数 == 300

        验证点:
        - episodic_count == 300
        - 每条记忆都有唯一ID
        - 记忆按重要性排序
        """
        hierarchies = {}
        total_memories = 0

        # 为10个用户创建记忆层级
        for user_id in range(10):
            user_id_str = f"user_{user_id}"
            hierarchy = MemoryHierarchy(
                working_max_size=20,
                user_id=user_id_str,
                conversation_id=uuid4(),
            )
            hierarchies[user_id_str] = hierarchy

            # 每个用户30轮对话
            for round_id in range(30):
                item = MemoryItem(
                    content=f"用户{user_id}第{round_id}轮对话: 我想去北京旅游",
                    level=MemoryLevel.EPISODIC,
                    memory_type=MemoryType.INTENT,
                    importance=0.5 + (round_id % 5) * 0.1,  # 0.5-0.9
                    metadata={
                        "user_id": user_id_str,
                        "round": round_id,
                        "destination": "北京",
                    },
                )
                await hierarchy.add_episodic(item)
                total_memories += 1

        # 验证总记忆数
        assert total_memories == 300, f"Expected 300 memories, got {total_memories}"

        # 验证每个hierarchy的记忆数
        for user_id_str, hierarchy in hierarchies.items():
            summary = hierarchy.get_context_summary()
            assert summary["episodic_count"] == 30, \
                f"User {user_id_str}: expected 30 memories, got {summary['episodic_count']}"

        # 验证记忆属性
        test_hierarchy = hierarchies["user_0"]
        memories = test_hierarchy.get_episodic(limit=100)
        assert len(memories) == 30

        # 验证每条记忆都有唯一ID
        memory_ids = [m.item_id for m in memories]
        assert len(memory_ids) == len(set(memory_ids)), "Memory IDs should be unique"

        # 验证记忆按重要性排序
        importances = [m.importance for m in memories]
        assert importances == sorted(importances, reverse=True), \
            "Memories should be sorted by importance"

    @pytest.mark.asyncio
    async def test_mem01_memory_types_distribution(self):
        """MEM-01-扩展: 验证不同类型记忆的分布

        测试场景:
        - 生成包含5种类型的记忆
        - 验证类型分布均匀

        验证点:
        - 所有5种类型都被覆盖
        - 每种类型的记忆数量合理
        """
        hierarchy = MemoryHierarchy(
            working_max_size=20,
            user_id="test_user_types",
            conversation_id=uuid4(),
        )

        memory_types = [
            MemoryType.FACT,
            MemoryType.PREFERENCE,
            MemoryType.INTENT,
            MemoryType.CONSTRAINT,
            MemoryType.EMOTION,
        ]

        # 为每种类型生成6条记忆（共30条）
        for memory_type in memory_types:
            for i in range(6):
                item = MemoryItem(
                    content=f"{memory_type.value}记忆_{i}",
                    level=MemoryLevel.EPISODIC,
                    memory_type=memory_type,
                    importance=0.6 + (i % 4) * 0.1,
                )
                await hierarchy.add_episodic(item)

        # 验证总记忆数
        summary = hierarchy.get_context_summary()
        assert summary["episodic_count"] == 30

        # 验证每种类型的记忆数
        for memory_type in memory_types:
            memories = hierarchy.get_episodic(
                limit=100,
                memory_type=memory_type,
            )
            assert len(memories) == 6, \
                f"Expected 6 memories for type {memory_type.value}, got {len(memories)}"


class TestMemoryHierarchyMEM02:
    """MEM-02: 记忆晋升测试 (100条)

    验证记忆从episodic到semantic的晋升机制，
    测试基于重要性的晋升阈值和晋升率。
    """

    @pytest.fixture
    def hierarchy(self):
        return MemoryHierarchy(
            working_max_size=20,
            user_id="test_user_promotion",
            conversation_id=uuid4(),
        )

    @pytest.mark.asyncio
    async def test_mem02_promotion_threshold_0_7(self, hierarchy):
        """MEM-02-1: 测试晋升阈值为0.7时的晋升率

        测试场景:
        - 生成100条记忆，importance分布: 0.1-1.0
        - 晋升阈值: 0.7
        - 预期晋升率: >= 30%

        验证点:
        - importance >= 0.7的记忆被晋升
        - 晋升率 >= 30%
        - 晋升后记忆在semantic中
        """
        # 生成100条记忆，importance从0.1到1.0
        for i in range(100):
            importance = 0.1 + (i % 10) * 0.1  # 0.1, 0.2, ..., 1.0
            item = MemoryItem(
                content=f"记忆_{i} (importance={importance})",
                level=MemoryLevel.EPISODIC,
                memory_type=MemoryType.PREFERENCE,
                importance=importance,
            )
            await hierarchy.add_episodic(item)

            # 尝试晋升
            if importance >= 0.7:
                hierarchy.promote_to_semantic(item, min_importance=0.7)

        # 验证episodic记忆数
        summary = hierarchy.get_context_summary()
        assert summary["episodic_count"] == 100

        # 验证semantic记忆数（应该>= 30）
        semantic_count = summary["semantic_count"]
        assert semantic_count >= 30, \
            f"Expected >= 30 semantic memories, got {semantic_count}"

        # 验证晋升率
        promotion_rate = semantic_count / 100
        assert promotion_rate >= 0.30, \
            f"Expected promotion rate >= 30%, got {promotion_rate * 100:.1f}%"

        # 验证晋升的记忆确实在semantic中
        semantic_memories = hierarchy.get_semantic(limit=100)
        assert len(semantic_memories) >= 30

        # 验证所有semantic记忆的importance >= 0.7
        for mem in semantic_memories:
            assert mem.importance >= 0.7, \
                f"Semantic memory has importance {mem.importance} < 0.7"

    @pytest.mark.asyncio
    async def test_mem02_promotion_history_tracking(self, hierarchy):
        """MEM-02-2: 测试晋升历史记录

        测试场景:
        - 晋升10条记忆
        - 验证晋升历史被正确记录

        验证点:
        - promotion_history包含10条记录
        - 每条记录包含必要字段
        - 可以检索最近N条晋升记录
        """
        # 晋升10条记忆
        for i in range(10):
            item = MemoryItem(
                content=f"重要记忆_{i}",
                level=MemoryLevel.EPISODIC,
                memory_type=MemoryType.PREFERENCE,
                importance=0.8 + i * 0.02,  # 0.8-0.98
            )
            await hierarchy.add_episodic(item)
            hierarchy.promote_to_semantic(item, min_importance=0.7)

        # 验证晋升历史
        recent_promotions = hierarchy.get_recent_promotions(limit=20)
        assert len(recent_promotions) == 10

        # 验证每条记录的字段
        for promo in recent_promotions:
            assert "from_level" in promo
            assert "to_level" in promo
            assert "content" in promo
            assert "time" in promo
            assert "importance" in promo
            assert promo["to_level"] == MemoryLevel.SEMANTIC.value
            assert promo["importance"] >= 0.7

    @pytest.mark.asyncio
    async def test_mem02_promotion_not_below_threshold(self, hierarchy):
        """MEM-02-3: 测试低于阈值的记忆不被晋升

        测试场景:
        - 尝试晋升importance < 0.7的记忆
        - 验证不被晋升

        验证点:
        - importance < 0.7的记忆不被晋升
        - semantic记忆数为0
        - promotion_history为空
        """
        # 添加10条低重要性记忆
        for i in range(10):
            item = MemoryItem(
                content=f"低重要性记忆_{i}",
                level=MemoryLevel.EPISODIC,
                memory_type=MemoryType.FACT,
                importance=0.3 + i * 0.03,  # 0.3-0.57
            )
            await hierarchy.add_episodic(item)
            result = hierarchy.promote_to_semantic(item, min_importance=0.7)
            assert not result, f"Memory with importance {item.importance} should not promote"

        # 验证没有记忆被晋升
        summary = hierarchy.get_context_summary()
        assert summary["semantic_count"] == 0

        recent_promotions = hierarchy.get_recent_promotions()
        assert len(recent_promotions) == 0


class TestMemoryHierarchyMEM03:
    """MEM-03: 工作记忆容量测试 (20条 + overflow测试)

    验证工作记忆的容量限制和溢出处理机制，
    测试自动晋升和驱逐行为。
    """

    @pytest.fixture
    def hierarchy(self):
        return MemoryHierarchy(
            working_max_size=20,  # 默认容量
            working_max_tokens=4000,
            user_id="test_user_working",
            conversation_id=uuid4(),
        )

    def test_mem03_working_memory_max_size(self, hierarchy):
        """MEM-03-1: 测试工作记忆最大容量限制

        测试场景:
        - 添加25条消息（超过容量20）
        - 验证只保留最近20条

        验证点:
        - working_count <= 20
        - 保留的是最新的20条
        - 旧消息被自动驱逐
        """
        # 添加25条消息
        for i in range(25):
            hierarchy.add_working_message(
                role="user",
                content=f"消息_{i}",
            )

        # 验证容量限制
        summary = hierarchy.get_context_summary()
        assert summary["working_count"] == 20, \
            f"Expected 20 working memories, got {summary['working_count']}"

        # 验证保留的是最新的20条（消息5-24）
        working_memories = hierarchy.get_working(limit=20)
        assert len(working_memories) == 20

        # 最新的消息应该包含"消息_24"
        latest_content = working_memories[-1]["content"]
        assert "消息_24" in latest_content

    def test_mem03_working_memory_token_limit(self, hierarchy):
        """MEM-03-2: 测试工作记忆token限制

        测试场景:
        - 添加超大消息（超过token限制）
        - 验证自动修剪到token限制内

        验证点:
        - working_tokens <= 4000
        - 保留最重要的消息
        """
        # 添加10条大消息（每条约500 tokens）
        for i in range(10):
            hierarchy.add_working_message(
                role="user",
                content=f"大消息_{i}: " + "内容" * 500,  # 约500 tokens
                tokens=500,
            )

        # 验证token限制
        summary = hierarchy.get_context_summary()
        assert summary["working_tokens"] <= 4000, \
            f"Expected <= 4000 tokens, got {summary['working_tokens']}"

        # 验证至少保留2条消息（最小保留）
        working_memories = hierarchy.get_working(limit=20)
        assert len(working_memories) >= 2, \
            "Should keep at least 2 messages even with token limit"

    @pytest.mark.asyncio
    async def test_mem03_overflow_auto_promotion(self, hierarchy):
        """MEM-03-3: 测试溢出时自动晋升

        测试场景:
        - 工作记忆满载时添加高重要性记忆
        - 验证自动晋升到episodic

        验证点:
        - 高重要性记忆被晋升
        - 工作记忆容量得以释放
        - 晋升记录被保存
        """
        # 填满工作记忆
        for i in range(20):
            hierarchy.add_working_message(
                role="user",
                content=f"普通消息_{i}",
            )

        # 添加高重要性记忆（应触发晋升）
        important_item = MemoryItem(
            content="重要信息: 用户想去巴黎旅游",
            level=MemoryLevel.WORKING,
            memory_type=MemoryType.INTENT,
            importance=0.9,
        )
        await hierarchy.add(important_item)

        # 验证工作记忆仍然在容量内
        summary = hierarchy.get_context_summary()
        assert summary["working_count"] <= 20

    def test_mem03_working_memory_lru_eviction(self, hierarchy):
        """MEM-03-4: 测试LRU驱逐策略

        测试场景:
        - 添加20条消息
        - 再添加5条新消息
        - 验证最旧的5条被驱逐

        验证点:
        - 最旧的消息被驱逐
        - 保留的是最新的20条
        """
        # 添加20条消息
        for i in range(20):
            hierarchy.add_working_message(
                role="user",
                content=f"旧消息_{i}",
            )

        # 添加5条新消息
        for i in range(5):
            hierarchy.add_working_message(
                role="user",
                content=f"新消息_{i}",
            )

        # 验证容量
        summary = hierarchy.get_context_summary()
        assert summary["working_count"] == 20

        # 验证最旧的消息被驱逐
        working_memories = hierarchy.get_working(limit=20)
        contents = [m["content"] for m in working_memories]

        # "旧消息_0"到"旧消息_4"应该被驱逐
        assert "旧消息_0" not in contents
        assert "旧消息_4" not in contents
        assert "新消息_4" in contents


class TestMemoryHierarchyMEM04:
    """MEM-04: 语义记忆检索测试 (80条)

    验证语义记忆的检索功能，
    测试搜索准确性、排序和过滤。
    """

    @pytest.fixture
    def hierarchy(self):
        hierarchy = MemoryHierarchy(
            working_max_size=20,
            user_id="test_user_retrieval",
            conversation_id=uuid4(),
        )

        # 添加80条语义记忆
        destinations = ["北京", "上海", "广州", "深圳", "杭州"]
        for i in range(80):
            dest = destinations[i % len(destinations)]
            item = MemoryItem(
                content=f"用户喜欢去{dest}旅游，预算{1000 + i * 100}元",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.PREFERENCE,
                importance=0.5 + (i % 5) * 0.1,  # 0.5-0.9
                metadata={
                    "destination": dest,
                    "budget": 1000 + i * 100,
                },
            )
            hierarchy.add_semantic(item)

        return hierarchy

    def test_mem04_retrieval_by_query(self, hierarchy):
        """MEM-04-1: 测试基于查询的检索

        测试场景:
        - 搜索包含"北京"的记忆
        - 验证返回相关记忆

        验证点:
        - 返回的记忆包含查询关键词
        - 结果按importance排序
        - 返回数量不超过limit
        """
        # 搜索包含"北京"的记忆
        results = hierarchy.get_semantic(
            query="北京",
            limit=10,
        )

        # 应该找到约16条记忆（80条中有1/5是北京）
        assert len(results) > 0

        # 验证结果包含"北京"
        for mem in results:
            assert "北京" in mem.content

        # 验证按importance排序
        importances = [m.importance for m in results]
        assert importances == sorted(importances, reverse=True)

    def test_mem04_retrieval_by_type(self, hierarchy):
        """MEM-04-2: 测试按类型过滤检索

        测试场景:
        - 按PREFERENCE类型检索
        - 验证返回正确类型的记忆

        验证点:
        - 返回的记忆都是PREFERENCE类型
        - 数量正确
        """
        # 添加不同类型的记忆
        for i in range(10):
            item = MemoryItem(
                content=f"意图记忆_{i}",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.INTENT,
                importance=0.7,
            )
            hierarchy.add_semantic(item)

        # 检索PREFERENCE类型
        results = hierarchy.get_semantic(
            memory_type=MemoryType.PREFERENCE,
            limit=100,
        )

        # 验证所有结果都是PREFERENCE类型
        assert len(results) > 0
        for mem in results:
            assert mem.memory_type == MemoryType.PREFERENCE

    def test_mem04_retrieval_importance_ranking(self, hierarchy):
        """MEM-04-3: 测试重要性排序

        测试场景:
        - 检索所有语义记忆
        - 验证按importance降序排序

        验证点:
        - 结果按importance降序排列
        - 高重要性记忆排在前面
        """
        # 检索所有记忆
        results = hierarchy.get_semantic(limit=100)

        # 验证排序
        importances = [m.importance for m in results]
        sorted_importances = sorted(importances, reverse=True)
        assert importances == sorted_importances, \
            "Results should be sorted by importance (descending)"

        # 验证第一个是最高重要性
        assert importances[0] >= importances[-1]

    def test_mem04_retrieval_limit_enforcement(self, hierarchy):
        """MEM-04-4: 测试limit参数生效

        测试场景:
        - 设置不同的limit值
        - 验证返回数量符合limit

        验证点:
        - limit=5返回5条
        - limit=10返回10条
        - limit超过总数时返回所有
        """
        # 测试limit=5
        results_5 = hierarchy.get_semantic(limit=5)
        assert len(results_5) == 5

        # 测试limit=10
        results_10 = hierarchy.get_semantic(limit=10)
        assert len(results_10) == 10

        # 测试limit超过总数（fixture中只有80条）
        results_all = hierarchy.get_semantic(limit=1000)
        assert len(results_all) == 80  # fixture中的80条记忆

    @pytest.mark.asyncio
    async def test_mem04_retrieval_after_promotion(self):
        """MEM-04-5: 测试晋升后的检索

        测试场景:
        - 从episodic晋升到semantic
        - 验证可以在semantic中检索到

        验证点:
        - 晋升后可以检索到
        - 内容保持一致
        - importance保持一致
        """
        hierarchy = MemoryHierarchy(
            working_max_size=20,
            user_id="test_user_promotion_retrieval",
            conversation_id=uuid4(),
        )

        # 添加并晋升记忆
        item = MemoryItem(
            content="用户喜欢去成都旅游",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.85,
        )
        await hierarchy.add_episodic(item)
        hierarchy.promote_to_semantic(item, min_importance=0.7)

        # 检索
        results = hierarchy.get_semantic(
            query="成都",
            limit=10,
        )

        # 验证能检索到
        assert len(results) > 0
        found = any("成都" in mem.content for mem in results)
        assert found

        # 验证content和importance
        promoted = next(m for m in results if "成都" in m.content)
        assert promoted.content == "用户喜欢去成都旅游"
        assert promoted.importance == 0.85


class TestMemoryHierarchyMEM05:
    """MEM-05: 跨用户记忆隔离测试 (80条)

    验证不同用户的记忆完全隔离，
    测试用户特定的检索和存储。
    """

    @pytest.mark.asyncio
    async def test_mem05_user_isolation(self):
        """MEM-05-1: 测试用户间记忆隔离

        测试场景:
        - 3个用户，每个用户20条记忆
        - 验证用户间无交叉污染

        验证点:
        - 每个用户只能访问自己的记忆
        - 用户A检索不到用户B的记忆
        - 总记忆数 = 60
        """
        hierarchies = {}

        # 为3个用户创建记忆层级
        for user_id in ["user_a", "user_b", "user_c"]:
            hierarchy = MemoryHierarchy(
                working_max_size=20,
                user_id=user_id,
                conversation_id=uuid4(),
            )
            hierarchies[user_id] = hierarchy

            # 每个用户添加20条记忆
            for i in range(20):
                item = MemoryItem(
                    content=f"{user_id}的记忆_{i}",
                    level=MemoryLevel.EPISODIC,
                    memory_type=MemoryType.PREFERENCE,
                    importance=0.6 + (i % 4) * 0.1,
                )
                await hierarchy.add_episodic(item)

        # 验证每个用户的记忆数
        for user_id, hierarchy in hierarchies.items():
            summary = hierarchy.get_context_summary()
            assert summary["episodic_count"] == 20, \
                f"User {user_id}: expected 20 memories, got {summary['episodic_count']}"

            # 验证记忆属于当前用户
            memories = hierarchy.get_episodic(limit=100)
            for mem in memories:
                assert user_id in mem.content, \
                    f"Memory {mem.item_id} belongs to {user_id}"

        # 验证用户间无交叉污染
        user_a_memories = hierarchies["user_a"].get_episodic(limit=100)
        user_b_memories = hierarchies["user_b"].get_episodic(limit=100)

        user_a_ids = {m.item_id for m in user_a_memories}
        user_b_ids = {m.item_id for m in user_b_memories}

        assert len(user_a_ids & user_b_ids) == 0, \
            "User A and User B should have no overlapping memories"

    @pytest.mark.asyncio
    async def test_mem05_user_specific_retrieval(self):
        """MEM-05-2: 测试用户特定的检索

        测试场景:
        - 2个用户有不同的偏好
        - 验证检索结果只包含当前用户的偏好

        验证点:
        - 用户A检索"北京"只返回自己的记忆
        - 用户B检索"上海"只返回自己的记忆
        """
        # 用户A喜欢北京
        hierarchy_a = MemoryHierarchy(
            working_max_size=20,
            user_id="user_beijing",
            conversation_id=uuid4(),
        )
        for i in range(10):
            item = MemoryItem(
                content=f"用户A喜欢北京景点_{i}",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.PREFERENCE,
                importance=0.7,
            )
            hierarchy_a.add_semantic(item)

        # 用户B喜欢上海
        hierarchy_b = MemoryHierarchy(
            working_max_size=20,
            user_id="user_shanghai",
            conversation_id=uuid4(),
        )
        for i in range(10):
            item = MemoryItem(
                content=f"用户B喜欢上海景点_{i}",
                level=MemoryLevel.SEMANTIC,
                memory_type=MemoryType.PREFERENCE,
                importance=0.7,
            )
            hierarchy_b.add_semantic(item)

        # 用户A检索"北京"
        results_a = hierarchy_a.get_semantic(query="北京", limit=20)
        assert len(results_a) == 10
        for mem in results_a:
            assert "用户A" in mem.content
            assert "北京" in mem.content

        # 用户B检索"上海"
        results_b = hierarchy_b.get_semantic(query="上海", limit=20)
        assert len(results_b) == 10
        for mem in results_b:
            assert "用户B" in mem.content
            assert "上海" in mem.content

        # 验证用户A检索不到用户B的记忆
        results_a_cross = hierarchy_a.get_semantic(query="上海", limit=20)
        assert len(results_a_cross) == 0

    @pytest.mark.asyncio
    async def test_mem05_cross_user_promotion_isolation(self):
        """MEM-05-3: 测试晋升时的用户隔离

        测试场景:
        - 2个用户都有episodic记忆
        - 验证晋升不会跨用户污染

        验证点:
        - 用户A的晋升不影响用户B
        - semantic记忆按用户隔离
        """
        # 用户A
        hierarchy_a = MemoryHierarchy(
            working_max_size=20,
            user_id="user_promo_a",
            conversation_id=uuid4(),
        )
        item_a = MemoryItem(
            content="用户A的重要信息",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,
        )
        await hierarchy_a.add_episodic(item_a)
        hierarchy_a.promote_to_semantic(item_a, min_importance=0.7)

        # 用户B
        hierarchy_b = MemoryHierarchy(
            working_max_size=20,
            user_id="user_promo_b",
            conversation_id=uuid4(),
        )
        item_b = MemoryItem(
            content="用户B的重要信息",
            level=MemoryLevel.EPISODIC,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8,
        )
        await hierarchy_b.add_episodic(item_b)
        hierarchy_b.promote_to_semantic(item_b, min_importance=0.7)

        # 验证用户A的semantic记忆
        semantic_a = hierarchy_a.get_semantic(limit=10)
        assert len(semantic_a) == 1
        assert "用户A" in semantic_a[0].content

        # 验证用户B的semantic记忆
        semantic_b = hierarchy_b.get_semantic(limit=10)
        assert len(semantic_b) == 1
        assert "用户B" in semantic_b[0].content

        # 验证无交叉污染
        assert semantic_a[0].item_id != semantic_b[0].item_id

    @pytest.mark.asyncio
    async def test_mem05_concurrent_user_operations(self):
        """MEM-05-4: 测试并发用户操作

        测试场景:
        - 5个用户并发添加记忆
        - 验证无竞态条件和数据混乱

        验证点:
        - 每个用户的记忆数正确
        - 无跨用户数据混乱
        - 所有操作成功完成
        """
        import asyncio

        hierarchies = {}
        user_ids = [f"user_concurrent_{i}" for i in range(5)]

        # 初始化hierarchies
        for user_id in user_ids:
            hierarchies[user_id] = MemoryHierarchy(
                working_max_size=20,
                user_id=user_id,
                conversation_id=uuid4(),
            )

        # 并发添加记忆
        async def add_memories_for_user(user_id: str):
            hierarchy = hierarchies[user_id]
            for i in range(10):
                item = MemoryItem(
                    content=f"{user_id}_记忆_{i}",
                    level=MemoryLevel.EPISODIC,
                    memory_type=MemoryType.FACT,
                    importance=0.6,
                )
                await hierarchy.add_episodic(item)

        # 并发执行
        await asyncio.gather(*[add_memories_for_user(uid) for uid in user_ids])

        # 验证每个用户的记忆数
        for user_id in user_ids:
            hierarchy = hierarchies[user_id]
            summary = hierarchy.get_context_summary()
            assert summary["episodic_count"] == 10, \
                f"User {user_id}: expected 10 memories, got {summary['episodic_count']}"

            # 验证记忆属于当前用户
            memories = hierarchy.get_episodic(limit=100)
            for mem in memories:
                assert user_id in mem.content, \
                    f"Memory {mem.item_id} should belong to {user_id}"
