"""ExamplesLoader - Few-shot 示例 YAML 加载器

功能:
- 从 YAML 文件加载 Few-shot 示例
- 内存缓存避免重复文件 I/O
- 优雅的错误处理和降级
"""

import logging
from pathlib import Path
from typing import Dict, List, Any

import yaml

logger = logging.getLogger(__name__)


class ExamplesLoader:
    """加载和管理 Few-shot 示例 YAML 文件.

    每个意图对应一个 YAML 文件，格式为:
    {intent: [{input: ..., output: ...}, ...]}

    Attributes:
        examples_dir: 示例文件目录
        _cache: 内存缓存字典
    """

    def __init__(self, examples_dir: Path):
        """初始化示例加载器.

        Args:
            examples_dir: 存放示例 YAML 文件的目录
        """
        self.examples_dir = examples_dir
        self._cache: Dict[str, List[Dict]] = {}

    def get_examples(self, intent: str) -> List[Dict]:
        """获取指定意图的示例列表.

        Args:
            intent: 意图标识 (如 'itinerary', 'query')

        Returns:
            示例列表，每个示例为 {input: str, output: str} 字典
            文件不存在或解析失败时返回空列表
        """
        # 检查缓存
        if intent in self._cache:
            return self._cache[intent]

        # 构建文件路径
        path = self.examples_dir / f"{intent}.yaml"
        if not path.exists():
            logger.warning(f"[ExamplesLoader] Examples file not found: {path}")
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            # 解析数据结构
            if data is None:
                # 空文件
                examples = []
            elif isinstance(data, dict):
                examples = data.get(intent, [])
            else:
                logger.warning(f"[ExamplesLoader] Unexpected data format in {path}")
                examples = []

            # 缓存结果
            self._cache[intent] = examples
            logger.debug(f"[ExamplesLoader] Loaded {len(examples)} examples for '{intent}'")
            return examples

        except yaml.YAMLError as e:
            logger.error(f"[ExamplesLoader] YAML parse error in {path}: {e}")
            return []
        except Exception as e:
            logger.error(f"[ExamplesLoader] Failed to load examples: {e}")
            return []

    def clear_cache(self) -> None:
        """清空缓存（用于测试或强制刷新）."""
        self._cache.clear()
        logger.debug("[ExamplesLoader] Cache cleared")

    def get_cached_intents(self) -> List[str]:
        """获取已缓存的意图列表."""
        return list(self._cache.keys())