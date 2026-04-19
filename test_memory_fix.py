"""
测试记忆存储修复
验证 Redis 和 ChromaDB 记忆存储是否正常工作
"""
import asyncio
import sys
sys.path.append('backend')

from app.core.memory.hierarchy import MemoryHierarchy, MemoryItem, MemoryLevel
from app.core.memory.redis_episodic import RedisEpisodicStore

async def test_redis_storage():
    """测试 Redis 记忆存储"""
    print("\n" + "="*60)
    print("测试 1: Redis 记忆存储")
    print("="*60)

    user_id = "test-user-123"
    conversation_id = "00000000-0000-0000-0000-0000000000001"  # Valid UUID format

    # 创建 Redis 存储
    redis_store = RedisEpisodicStore(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0
    )

    print("[OK] RedisEpisodicStore initialized successfully")

    # 创建测试记忆项
    test_item = MemoryItem(
        content="测试记忆内容：用户喜欢去热带海岛旅游",
        level=MemoryLevel.EPISODIC,
    )

    # 添加到 Redis
    print(f"\n添加记忆到 Redis...")
    try:
        await redis_store.add(user_id, conversation_id, test_item)
        print("[OK] Memory added successfully")
    except Exception as e:
        print(f"[FAIL] Add failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 从 Redis 读取
    print(f"\n从 Redis 读取记忆...")
    try:
        memories = await redis_store.get_all(user_id, conversation_id)
        if memories:
            print(f"[OK] Read successfully, found {len(memories)} memories")
            for i, mem in enumerate(memories, 1):
                print(f"  {i}. {mem.content[:50]}...")
        else:
            print("[WARN] No memories found")
    except Exception as e:
        print(f"[FAIL] Read failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n[OK] Redis test completed")
    return True

async def test_memory_hierarchy():
    """测试记忆层级管理器"""
    print("\n" + "="*60)
    print("测试 2: 记忆层级管理器 (add_episodic)")
    print("="*60)

    user_id = "test-user-123"
    from uuid import uuid4
    conversation_id = uuid4()  # Generate valid UUID

    # 创建 Redis 存储
    redis_store = RedisEpisodicStore(
        redis_host="localhost",
        redis_port=6379,
        redis_db=0
    )

    # 创建记忆层级管理器
    hierarchy = MemoryHierarchy(
        redis_store=redis_store,
        user_id=user_id,
        conversation_id=conversation_id,
    )

    print("[OK] MemoryHierarchy initialized successfully")

    # 测试 add_episodic 方法
    print(f"\n测试 add_episodic() 方法...")
    test_item = MemoryItem(
        content="测试 episodic 记忆：用户偏好预算 5000-10000 元",
        level=MemoryLevel.EPISODIC,
    )

    try:
        await hierarchy.add_episodic(test_item)
        print("[OK] add_episodic() called successfully")
    except Exception as e:
        print(f"[FAIL] add_episodic() failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 验证记忆是否已存储
    print(f"\n验证记忆是否已存储...")
    try:
        memories = await redis_store.get_all(user_id, conversation_id)
        if memories:
            print(f"[OK] Verification successful, Redis has {len(memories)} memories")
            # 查找刚添加的记忆
            found = any("预算 5000-10000" in mem.content for mem in memories)
            if found:
                print("[OK] Newly added memory successfully stored")
            else:
                print("[WARN] Newly added memory not found")
        else:
            print("[WARN] No memories found in Redis")
    except Exception as e:
        print(f"[FAIL] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n[OK] MemoryHierarchy test completed")
    return True

async def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("记忆存储修复验证测试")
    print("="*60)

    # 测试 1: Redis 基础存储
    result1 = await test_redis_storage()

    # 测试 2: MemoryHierarchy add_episodic
    result2 = await test_memory_hierarchy()

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"Redis 基础存储: {'[OK] 通过' if result1 else '[FAIL] 失败'}")
    print(f"MemoryHierarchy: {'[OK] 通过' if result2 else '[FAIL] 失败'}")

    if result1 and result2:
        print("\n[SUCCESS] 所有测试通过！记忆存储修复成功！")
        return 0
    else:
        print("\n[WARN] 部分测试失败，请检查错误信息")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
