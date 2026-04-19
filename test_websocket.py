"""测试后端 WebSocket 阶段状态发送"""
import asyncio
import websockets
import json
import sys

# 设置 UTF-8 编码输出
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

async def test_websocket():
    uri = "ws://localhost:8000/ws/chat"
    async with websockets.connect(uri) as websocket:
        # 发送测试消息
        message = {
            "type": "message",
            "session_id": "test_session_123",
            "content": "你好",
            "user_id": None
        }

        print(f"发送消息: {message}")
        await websocket.send(json.dumps(message))

        print("\n=== 接收响应 ===")
        stage_count = 0
        chunk_count = 0

        while True:
            try:
                response = await asyncio.wait_for(websocket.recv(), timeout=30)
                data = json.loads(response)

                if data.get("type") == "stage":
                    stage_count += 1
                    stage = data.get("stage", {})
                    print(f"[阶段 {stage_count}] {stage.get('label')} | {stage.get('name')} | status={stage.get('status')}")

                elif data.get("type") == "delta":
                    chunk_count += 1
                    if chunk_count == 1:
                        print(f"\n[LLM 开始流式输出]")

                elif data.get("type") == "done":
                    print(f"\n=== 完成 ===")
                    print(f"总阶段数: {stage_count}")
                    print(f"总chunk数: {chunk_count}")
                    break

                elif data.get("type") == "error":
                    print(f"[错误] {data.get('error')}")
                    break

            except asyncio.TimeoutError:
                print("[超时] 30秒内未收到响应")
                break
            except Exception as e:
                print(f"[异常] {e}")
                break

if __name__ == "__main__":
    asyncio.run(test_websocket())
