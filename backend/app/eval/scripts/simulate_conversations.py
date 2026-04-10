"""
模拟真实对话产生评估数据

通过发送实际聊天请求到后端服务器，产生轨迹数据，
用于测试评估系统的实际指标。
"""
import asyncio
import aiohttp
import json
import time
from datetime import datetime, timezone, timedelta


# 后端服务器地址
BACKEND_URL = "http://localhost:8000"


# 模拟对话脚本
CONVERSATION_SCRIPTS = [
    {
        "user_id": "test_user_001",
        "messages": [
            "你好",
            "帮我规划北京三日游",
            "我想去故宫和长城",
            "还有颐和园",
            "预算大概3000元",
            "喜欢历史景点",
        ]
    },
    {
        "user_id": "test_user_002",
        "messages": [
            "上海明天天气怎么样",
            "这周会下雨吗",
            "杭州天气如何",
        ]
    },
    {
        "user_id": "test_user_003",
        "messages": [
            "怎么从北京去上海",
            "高铁要多少钱",
            "飞机票价格",
        ]
    },
    {
        "user_id": "test_user_004",
        "messages": [
            "推荐成都的酒店",
            "不要太贵的",
            "靠近市中心的",
            "西安有什么特色住宿",
        ]
    },
    {
        "user_id": "test_user_005",
        "messages": [
            "我想去成都玩4天",
            "喜欢吃辣",
            "想体验当地文化",
            "预算5000元以内",
            "帮我安排一下行程",
        ]
    },
    {
        "user_id": "test_user_006",
        "messages": [
            "杭州西湖有什么好玩的",
            "门票多少钱",
            "玩一天够吗",
        ]
    },
    {
        "user_id": "test_user_007",
        "messages": [
            "我喜欢吃辣",
            "不喜欢人多的景点",
            "比较喜欢安静的地方",
        ]
    },
    {
        "user_id": "test_user_008",
        "messages": [
            "云南大理丽江6日游",
            "喜欢自然风光",
            "想要轻松一点的行程",
            "推荐一些特色美食",
        ]
    },
]


async def send_chat_message(session, user_id, message, conversation_id):
    """发送聊天消息"""
    url = f"{BACKEND_URL}/api/agent/chat"
    payload = {
        "message": message,
        "conversation_id": conversation_id,
        "user_id": user_id,
    }

    try:
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                # 读取完整响应
                await resp.text()
                return True
            else:
                text = await resp.text()
                print(f"    [ERROR] Status {resp.status}: {text[:50]}")
                return False
    except Exception as e:
        print(f"    [ERROR] {e}")
        return False


async def simulate_conversation(session, script):
    """模拟一个完整对话"""
    print(f"\n用户 {script['user_id']}:")
    conv_id = f"test_conv_{script['user_id']}"

    for i, message in enumerate(script['messages'], 1):
        print(f"  [{i}] {message}")
        success = await send_chat_message(session, script['user_id'], message, conv_id)
        if success:
            print(f"      -> [OK]")
        else:
            print(f"      -> [FAIL]")
        # 稍微延迟，避免请求过快
        await asyncio.sleep(1)


async def check_eval_data(session):
    """检查评估数据"""
    print("\n" + "="*60)
    print("检查评估数据...")
    print("="*60)

    # 需要先登录获取 token
    login_url = f"{BACKEND_URL}/api/v1/auth/login"
    login_payload = {
        "email": "2781764566@qq.com",
        "password": "123456"
    }

    try:
        async with session.post(login_url, json=login_payload) as resp:
            if resp.status != 200:
                print("  [!] 需要先创建测试用户")
                print("  请运行: python -m app.eval.scripts.create_test_user")
                return

            data = await resp.json()
            token = data.get('access_token')
            if not token:
                print("  [!] 登录失败")
                return

        headers = {"Authorization": f"Bearer {token}"}

        # 获取评估指标
        async with session.get(f"{BACKEND_URL}/api/v1/eval/metrics", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                print(f"\n评估指标:")
                print(f"  总轨迹数: {data.get('total_trajectories', 0)}")
                print(f"  Token 降低率: {data.get('token_reduction_rate', 0)}%")
                print(f"  超限次数: {data.get('overflow_count', 0)}")
                print(f"  验证通过率: {data.get('verification_pass_rate', 'N/A')}")
            else:
                print(f"  [!] 获取指标失败: {resp.status}")

    except Exception as e:
        print(f"  [!] 检查失败: {e}")


async def main():
    print("="*60)
    print("模拟真实对话产生评估数据")
    print("="*60)
    print(f"后端地址: {BACKEND_URL}")
    print(f"对话脚本数: {len(CONVERSATION_SCRIPTS)}")
    print(f"总消息数: {sum(len(s['messages']) for s in CONVERSATION_SCRIPTS)}")

    # 检查后端是否运行
    print("\n检查后端服务...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BACKEND_URL}/health") as resp:
                if resp.status != 200:
                    print("[!] 后端服务未正常响应")
                    print("    请先启动: cd backend && python -m uvicorn app.main:app --reload --port 8000")
                    return
                print("[OK] 后端服务正常")
    except Exception as e:
        print(f"[!] 无法连接到后端: {e}")
        print("    请先启动: cd backend && python -m uvicorn app.main:app --reload --port 8000")
        return

    # 执行对话模拟
    print("\n开始模拟对话...")
    async with aiohttp.ClientSession() as session:
        for script in CONVERSATION_SCRIPTS:
            await simulate_conversation(session, script)
            await asyncio.sleep(0.5)

    print("\n" + "="*60)
    print("对话模拟完成!")
    print("="*60)

    # 等待数据保存
    print("\n等待数据保存...")
    await asyncio.sleep(2)

    # 检查评估数据
    await check_eval_data(session)

    print("\n提示: 刷新前端 /eval 页面查看数据")


if __name__ == "__main__":
    asyncio.run(main())
