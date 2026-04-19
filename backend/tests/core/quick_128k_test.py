"""快速128k窗口压缩测试"""

import sys
import asyncio
sys.path.insert(0, '.')

from app.core.context_mgmt.guard import ContextGuard
from app.core.context_mgmt.config import ContextConfig
from app.core.context_mgmt.tokenizer import TokenEstimator

async def quick_test():
    print('Starting 128k window compression test...')

    config = ContextConfig(window_size=128000, compress_threshold=0.75)
    guard = ContextGuard(config=config)
    guard.set_conv_id('quick_test')

    # Create huge message
    huge_message = 'This is a long message for testing compression strategy.' * 10000
    message_tokens = TokenEstimator.estimate(huge_message)
    print(f'Single message tokens: {message_tokens:,}')

    # Simulate message list
    messages = [
        {'role': 'system', 'content': 'You are an AI assistant'},
        {'role': 'user', 'content': huge_message},
        {'role': 'assistant', 'content': 'I understand, this is very long content.' * 1000},
    ]

    current_tokens = TokenEstimator.estimate_messages(messages)
    print(f'Initial tokens: {current_tokens:,} ({current_tokens/128000:.1%})')

    # Continue adding messages until compression triggers
    for i in range(5):
        new_messages = [
            {'role': 'user', 'content': huge_message},
            {'role': 'assistant', 'content': 'I understand, this is very long content.' * 1000},
        ]
        messages.extend(new_messages)

        current_tokens = TokenEstimator.estimate_messages(messages)
        usage_ratio = current_tokens / 128000
        threshold = 96000

        print(f'Round {i+1}: {current_tokens:,} ({usage_ratio:.1%}) - ', end='')

        if current_tokens >= threshold:
            print(f'EXCEEDS THRESHOLD!')

            # Execute compression
            compressed, was_compressed = await guard.post_process(messages)
            compressed_tokens = TokenEstimator.estimate_messages(compressed)

            print(f'Compression result: {current_tokens:,} -> {compressed_tokens:,} (saved {current_tokens-compressed_tokens:,} tokens)')
            print(f'Post-compression usage: {compressed_tokens/128000:.1%}')
            break
        else:
            print(f'Below threshold')

    print('Test completed!')

if __name__ == '__main__':
    asyncio.run(quick_test())