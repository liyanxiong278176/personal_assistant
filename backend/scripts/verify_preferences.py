"""验证脚本: 确保偏好和记忆功能正常工作

运行方式:
1. 确保后端服务运行: cd backend && python -m uvicorn app.main:app --reload
2. 运行此脚本: python backend/scripts/verify_preferences.py
3. 脚本会输出测试用户ID，用于浏览器测试
"""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.orchestrator import MasterOrchestrator
from app.db.postgres import create_user, update_preferences, get_preferences
from app.services.memory_service import memory_service


async def main():
    print("=" * 70)
    print("偏好和记忆功能验证")
    print("=" * 70)

    # 1. 创建测试用户
    user_id = await create_user()
    conversation_id = 'verify-test-conv'

    # 2. 设置测试偏好
    test_prefs = {
        'budget': 'medium',
        'interests': ['history', 'food', 'art'],
        'style': 'relaxed',
        'travelers': 2
    }
    await update_preferences(user_id, test_prefs)

    print(f"\n[1] 测试用户创建成功")
    print(f"    User ID: {user_id}")
    print(f"    偏好设置: {test_prefs}")

    # 3. 存储测试对话（记忆）
    await memory_service.store_message(
        user_id=user_id,
        conversation_id=conversation_id,
        role='user',
        content='我计划去北京旅游，喜欢历史文化和美食'
    )
    await memory_service.store_message(
        user_id=user_id,
        conversation_id=conversation_id,
        role='assistant',
        content='好的，我会根据您的偏好推荐相关景点'
    )

    print(f"\n[2] 对话记忆已存储")

    # 4. 检索并显示
    retrieved = await get_preferences(user_id)
    context = await memory_service.build_context_prompt(user_id, conversation_id)

    print(f"\n[3] 数据验证:")
    print(f"    偏好正确存储: {retrieved.get('budget') == 'medium'}")
    print(f"    兴趣正确存储: {retrieved.get('interests') == ['history', 'food', 'art']}")

    # 5. 显示系统提示词
    orchestrator = MasterOrchestrator()
    system_prompt = orchestrator._build_system_prompt(retrieved, context)

    print(f"\n[4] LLM系统提示词:")
    print("-" * 70)
    print(system_prompt)
    print("-" * 70)

    # 6. 浏览器测试说明
    print(f"\n[5] 浏览器测试步骤:")
    print(f"    1. 打开浏览器控制台 (F12)")
    print(f"    2. 运行以下代码设置测试用户:")
    print(f"       localStorage.setItem('travel_assistant_user_id', '{user_id}')")
    print(f"    3. 刷新页面")
    print(f"    4. 进入设置页面，应该看到:")
    print(f"       - 预算: 舒适型")
    print(f"       - 兴趣: 历史文化, 美食体验, 艺术展览")
    print(f"       - 风格: 悠闲放松")
    print(f"       - 人数: 2人")
    print(f"    5. 进入聊天页面，发送: \"推荐一些北京的景点\"")
    print(f"    6. 回复应该考虑你的偏好(历史文化、美食)")

    print(f"\n[6] 测试完成后清理:")
    print(f"    在控制台运行: localStorage.removeItem('travel_assistant_user_id')")

    print(f"\n" + "=" * 70)
    print(f"验证完成! User ID: {user_id}")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())
