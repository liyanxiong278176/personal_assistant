"""缓存层集成测试 - 测试与QueryEngine的集成"""
import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.core.query_engine import QueryEngine
from app.core.cache.manager import CacheManager


@pytest.fixture
def mock_cache_manager():
    """模拟CacheManager"""
    manager = Mock()
    manager.get_session = AsyncMock(return_value=None)
    manager.set_session = AsyncMock()
    manager.get_circuit_state = Mock(return_value="closed")
    return manager


@pytest.mark.asyncio
async def test_query_engine_load_history_from_cache(mock_cache_manager):
    """测试QueryEngine从缓存加载历史"""
    # 模拟缓存命中
    mock_cache_manager.get_session.return_value = {
        "messages": [
            {"role": "user", "content": "我想去北京"},
            {"role": "assistant", "content": "好的"}
        ],
        "updated_at": 123.0
    }

    engine = QueryEngine()
    engine._cache_manager = mock_cache_manager
    engine._phase2_enabled = True
    engine._conversation_history = {}

    history = await engine._load_history_from_db(str(uuid4()))

    assert len(history) == 2
    assert history[0]["content"] == "我想去北京"
    mock_cache_manager.get_session.assert_called_once()


@pytest.mark.asyncio
async def test_query_engine_cache_miss_loads_from_db():
    """测试缓存未命中时从数据库加载"""
    mock_manager = Mock()
    mock_manager.get_session = AsyncMock(return_value=None)  # 缓存未命中
    mock_manager.set_session = AsyncMock()

    mock_message_repo = Mock()
    mock_message_repo.get_by_conversation = AsyncMock(return_value=[])

    engine = QueryEngine()
    engine._cache_manager = mock_manager
    engine._phase2_enabled = True
    engine._message_repo = mock_message_repo
    engine._conversation_history = {}

    history = await engine._load_history_from_db(str(uuid4()))

    mock_manager.get_session.assert_called_once()
    mock_message_repo.get_by_conversation.assert_called_once()


@pytest.mark.asyncio
async def test_query_engine_writeback_to_cache():
    """测试异步写回缓存"""
    mock_manager = Mock()
    mock_manager.get_session = AsyncMock(return_value=None)
    mock_manager.set_session = AsyncMock()

    from app.db.message_repo import Message
    from datetime import datetime

    conv_id = uuid4()
    mock_messages = [
        Message(
            id=uuid4(),
            conversation_id=conv_id,
            user_id="test",
            role="user",
            content="测试消息",
            tokens=10,
            created_at=datetime.utcnow()
        )
    ]

    mock_message_repo = Mock()
    mock_message_repo.get_by_conversation = AsyncMock(return_value=mock_messages)

    engine = QueryEngine()
    engine._cache_manager = mock_manager
    engine._phase2_enabled = True
    engine._message_repo = mock_message_repo
    engine._conversation_history = {}

    history = await engine._load_history_from_db(str(conv_id))

    # 等待异步写回完成
    await asyncio.sleep(0.1)

    # 验证set_session被调用
    assert mock_manager.set_session.called
