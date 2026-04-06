"""工具执行器

支持并行工具执行和错误处理。
"""

import asyncio
import logging
from typing import Any, Dict

from .registry import ToolRegistry
from .base import Tool

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """工具执行错误"""

    def __init__(self, tool_name: str, original_error: Exception):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' execution failed: {original_error}")


class ToolExecutor:
    """工具执行器

    负责执行工具调用，支持并行执行和错误处理。
    """

    def __init__(self, registry: ToolRegistry, cache: Any = None):
        """初始化工具执行器

        Args:
            registry: 工具注册表
            cache: 可选的缓存对象，需提供 get(key) 方法
        """
        self._registry = registry
        self._cache = cache
        logger.info("[ToolExecutor] Initialized")

    async def execute(self, tool_name: str, **kwargs) -> Any:
        """执行单个工具

        Args:
            tool_name: 工具名称
            **kwargs: 工具参数

        Returns:
            工具执行结果

        Raises:
            ToolExecutionError: 工具执行失败
            ValueError: 工具不存在
        """
        tool = self._registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool '{tool_name}' not found in registry")

        try:
            logger.debug(f"[ToolExecutor] Executing tool: {tool_name} with kwargs: {kwargs}")
            result = await tool.execute(**kwargs)
            logger.debug(f"[ToolExecutor] Tool {tool_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"[ToolExecutor] Tool {tool_name} failed: {e}")
            raise ToolExecutionError(tool_name, e) from e

    async def execute_parallel(self, calls: list["ToolCall"]) -> Dict[str, Any]:
        """并行执行工具调用

        Args:
            calls: 工具调用列表，ToolCall 对象列表

        Returns:
            工具名称到执行结果的映射，格式为:
            {
                "tool_name": result,  # 成功执行的工具
                "tool_name": {"error": error_message, "original_error": exception},  # 失败的工具
            }

        Example:
            >>> executor = ToolExecutor(registry)
            >>> from app.core.llm import ToolCall
            >>> calls = [
            ...     ToolCall(id="1", name="search_weather", arguments={"city": "北京"}),
            ...     ToolCall(id="2", name="search_poi", arguments={"keyword": "景点"}),
            ... ]
            >>> results = await executor.execute_parallel(calls)
        """
        if not calls:
            return {}

        tasks = [self._execute_call(call) for call in calls]
        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results: Dict[str, Any] = {}
        for i, result in enumerate(results_list):
            tool_name = calls[i].name
            if isinstance(result, Exception):
                logger.error(f"[ToolExecutor] Parallel execution error for {tool_name}: {result}")
                original_error = result
                if isinstance(result, ToolExecutionError):
                    original_error = result.original_error
                results[tool_name] = {
                    "error": str(result),
                    "original_error": repr(original_error),
                }
            else:
                results[tool_name] = result

        return results

    async def execute_with_retry(
        self,
        tool_name: str,
        max_retries: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        """带重试的工具执行

        Args:
            tool_name: 工具名称
            max_retries: 最大重试次数
            **kwargs: 工具参数

        Returns:
            执行结果，包含 success、data/retried 字段
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                result = await self.execute(tool_name, **kwargs)
                return {
                    "success": True,
                    "data": result,
                    "retried": attempt > 0
                }
            except Exception as e:
                last_error = e
                if attempt < max_retries and self._is_retryable(e):
                    await asyncio.sleep(1)
                    continue
                break

        return {
            "success": False,
            "error": str(last_error),
            "retried": max_retries
        }

    def _is_retryable(self, error: Exception) -> bool:
        """判断错误是否可重试

        Args:
            error: 异常对象

        Returns:
            是否可重试
        """
        error_str = str(error).lower()
        retryable_keywords = ["timeout", "network", "connection", "rate limit", "429", "503"]
        return any(kw in error_str for kw in retryable_keywords)

    async def execute_with_fallback(
        self,
        tool_name: str,
        cache_key: str = None,
        **kwargs
    ) -> Dict[str, Any]:
        """带降级的工具执行

        优先执行工具，失败时尝试从缓存读取。

        Args:
            tool_name: 工具名称
            cache_key: 缓存键，不提供时使用 tool_name
            **kwargs: 工具参数

        Returns:
            执行结果，包含 success、data、from_cache、error 字段
        """
        try:
            result = await self.execute(tool_name, **kwargs)
            return {
                "success": True,
                "data": result,
                "from_cache": False,
                "error": None
            }
        except Exception as e:
            # Graceful degradation: try cache
            if self._cache is not None:
                key = cache_key if cache_key is not None else tool_name
                cached = self._cache.get(key)
                if cached is not None:
                    return {
                        "success": True,
                        "data": cached,
                        "from_cache": True,
                        "error": None
                    }
            return {
                "success": False,
                "data": None,
                "from_cache": False,
                "error": str(e)
            }

    async def _execute_call(self, call: "ToolCall") -> Any:
        """执行单个工具调用

        Args:
            call: ToolCall 对象

        Returns:
            工具执行结果
        """
        tool_name = call.name
        try:
            return await self.execute(tool_name, **call.arguments)
        except (ToolExecutionError, ValueError) as e:
            raise e
        except Exception as e:
            logger.exception(f"[ToolExecutor] Unexpected error executing {tool_name}")
            raise ToolExecutionError(tool_name, e) from e
