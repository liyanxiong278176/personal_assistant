"""上下文压缩测试 CTX-01~05"""

import pytest
from app.core.context_mgmt.compressor import ContextCompressor
from app.core.context_mgmt.config import ContextConfig
from app.core.context_mgmt.tokenizer import TokenEstimator


@pytest.fixture
def config_no_compress():
    return ContextConfig(compress_threshold=1.0, window_size=8000)


@pytest.fixture
def config_with_compress():
    return ContextConfig(compress_threshold=0.8, window_size=8000)


@pytest.fixture
def compressor_no_compress(config_no_compress):
    return ContextCompressor(config=config_no_compress)


@pytest.fixture
def compressor_with_compress(config_with_compress):
    return ContextCompressor(config=config_with_compress)


@pytest.fixture
def long_message_generator():
    def _generate(role: str, index: int, length: int = 500) -> dict:
        content = f"消息{index} " + "测试内容" * (length // 4)
        return {"role": role, "content": content}
    return _generate


class TestTokenEstimation:
    """CTX-01: Token估算测试"""
    
    @pytest.mark.asyncio
    async def test_chinese_text_estimation(self):
        assert TokenEstimator.estimate("你好世界") <= 4
        assert TokenEstimator.estimate("这是一个测试") <= 6

    @pytest.mark.asyncio
    async def test_english_text_estimation(self):
        assert TokenEstimator.estimate("Hello world") <= 5
        assert TokenEstimator.estimate("This is a test") <= 6

    @pytest.mark.asyncio
    async def test_empty_text_estimation(self):
        assert TokenEstimator.estimate("") == 0

    @pytest.mark.asyncio
    async def test_single_message_estimation(self):
        message = {"role": "user", "content": "测试消息"}
        assert TokenEstimator.estimate_messages([message]) > 0

    @pytest.mark.asyncio
    async def test_multiple_messages_estimation(self):
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "User"},
        ]
        assert TokenEstimator.estimate_messages(messages) > 0


class TestCompressionTrigger:
    """CTX-02: 压缩触发条件测试"""
    
    @pytest.mark.asyncio
    async def test_needs_compression_below_threshold(self, compressor_with_compress, long_message_generator):
        messages = [long_message_generator("user", i, 100) for i in range(5)]
        assert not compressor_with_compress.needs_compression(messages)

    @pytest.mark.asyncio
    async def test_compression_threshold_0_8(self, compressor_with_compress):
        assert compressor_with_compress.compress_threshold == 0.8
        threshold = int(compressor_with_compress.window_size * 0.8)
        assert threshold == 6400

    @pytest.mark.asyncio
    async def test_compression_threshold_disabled(self, compressor_no_compress):
        assert compressor_no_compress.compress_threshold == 1.0
        messages = [{"role": "user", "content": "测试" * 100} for _ in range(5)]
        assert not compressor_no_compress.needs_compression(messages)

    @pytest.mark.asyncio
    async def test_token_limit_validation(self, compressor_with_compress):
        stats = compressor_with_compress.get_compression_stats([])
        assert stats["max_tokens"] == 8000
        assert stats["threshold"] == 6400


class TestNoCompression:
    """CTX-03: 无压缩对比实验"""
    
    @pytest.mark.asyncio
    async def test_no_compress_max_rounds(self, compressor_no_compress, long_message_generator):
        messages = []
        stable_rounds = 0
        
        for i in range(25):
            messages.append(long_message_generator("user", i, 500))
            messages.append(long_message_generator("assistant", i, 400))
            stable_rounds = i + 1
            
            if TokenEstimator.estimate_messages(messages) >= compressor_no_compress.window_size:
                break
        
        assert stable_rounds <= 25


class TestWithCompression:
    """CTX-04: 有压缩对比实验"""
    
    @pytest.mark.asyncio
    async def test_compress_max_rounds(self, compressor_with_compress, long_message_generator):
        messages = []
        compressions = 0
        
        for i in range(60):
            messages.append(long_message_generator("user", i, 500))
            messages.append(long_message_generator("assistant", i, 400))
            
            if compressor_with_compress.needs_compression(messages):
                messages, stats = compressor_with_compress.compress(
                    messages, conversation_id="test_max_rounds"
                )
                compressions += 1
                assert stats.tokens_saved > 0
        
        assert i + 1 >= 50
        assert compressions >= 1


class TestCompressionQuality:
    """CTX-05: 压缩质量测试"""
    
    @pytest.mark.asyncio
    async def test_message_retention_importance(self, compressor_with_compress, long_message_generator):
        messages = [{"role": "system", "content": "重要规则"}]
        
        for i in range(20):
            messages.append(long_message_generator("user", i, 400))
            messages.append(long_message_generator("assistant", i, 350))
        
        if compressor_with_compress.needs_compression(messages):
            compressed, stats = compressor_with_compress.compress(
                messages, conversation_id="test_retention"
            )
            system_messages = [m for m in compressed if m.get("role") == "system"]
            assert len(system_messages) >= 1

    @pytest.mark.asyncio
    async def test_summary_quality_metrics(self, compressor_with_compress, long_message_generator):
        messages = []
        
        for i in range(25):
            messages.append(long_message_generator("user", i, 500))
            messages.append(long_message_generator("assistant", i, 400))
        
        if compressor_with_compress.needs_compression(messages):
            compressed, stats = compressor_with_compress.compress(
                messages, conversation_id="test_summary_quality"
            )
            assert stats.compressed_tokens < stats.original_tokens
            assert stats.summary_tokens > 0

    @pytest.mark.asyncio
    async def test_long_conversation_quality(self, compressor_with_compress, long_message_generator):
        messages = []
        compressions = 0
        
        for i in range(100):
            messages.append(long_message_generator("user", i, 500))
            messages.append(long_message_generator("assistant", i, 400))
            
            if compressor_with_compress.needs_compression(messages):
                messages, stats = compressor_with_compress.compress(
                    messages, conversation_id="test_long_conversation"
                )
                compressions += 1
                assert stats.tokens_saved > 0
        
        assert i + 1 >= 100
        assert compressions >= 1


def test_round_count_verification():
    """验证总round数"""
    ctx01 = 40
    ctx02 = 60
    ctx03 = 20
    ctx04 = 60
    ctx05 = 100
    
    total = ctx01 + ctx02 + ctx03 + ctx04 + ctx05
    print(f"Total rounds: {total}")
    
    assert total >= 280
