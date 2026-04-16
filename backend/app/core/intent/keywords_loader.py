"""KeywordsLoader - YAML-based hot-reload keyword configuration loader.

Supports:
- File modification time detection for auto-reload
- Positive and negative keywords (exclusion rules)
- Regex patterns for intent classification
- Graceful fallback on errors
"""

import logging
import yaml
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)


class KeywordsLoader:
    """关键词配置热加载器.

    功能特性:
    1. 检测配置文件修改时间，自动重载
    2. 内存缓存配置，减少文件 I/O
    3. 支持正向关键词和负向关键词（排除规则）
    4. 支持正则模式增强识别
    """

    def __init__(self, config_path: str | None = None):
        """初始化配置加载器.

        Args:
            config_path: keywords.yaml 配置文件路径
        """
        if config_path is None:
            # 默认路径
            config_path = Path(__file__).parent / "config" / "keywords.yaml"

        self.config_path = Path(config_path)
        self._keywords_cache: Dict[str, Dict[str, Any]] = {}
        self._patterns_cache: Dict[str, List[str]] = {}
        self._last_mtime: float = 0
        self._loaded: bool = False

        logger.info(f"[KeywordsLoader] 初始化，配置路径: {self.config_path}")

    def _should_reload(self) -> bool:
        """检查配置文件是否被修改.

        Returns:
            True if file was modified since last load
        """
        if not self.config_path.exists():
            logger.warning(f"[KeywordsLoader] 配置文件不存在: {self.config_path}")
            return False

        if not self._loaded:
            return True

        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._last_mtime

    def _load_config(self) -> Dict[str, Any]:
        """从 YAML 文件加载配置.

        Returns:
            配置字典
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self._last_mtime = self.config_path.stat().st_mtime
            self._loaded = True

            # 解析关键词
            self._keywords_cache = config.get("keywords", {})
            self._patterns_cache = config.get("patterns", {})

            logger.info(
                f"[KeywordsLoader] 配置已加载: "
                f"{len(self._keywords_cache)} 个意图关键词, "
                f"{len(self._patterns_cache)} 个意图模式"
            )

            return config

        except FileNotFoundError:
            logger.error(f"[KeywordsLoader] 配置文件不存在: {self.config_path}")
            self._load_defaults()
            return {"keywords": self._keywords_cache, "patterns": self._patterns_cache}

        except yaml.YAMLError as e:
            logger.error(f"[KeywordsLoader] YAML 解析失败: {e}")
            self._load_defaults()
            return {"keywords": self._keywords_cache, "patterns": self._patterns_cache}

    def _load_defaults(self) -> None:
        """加载默认配置（降级方案）."""
        # 最小默认配置，确保系统可用
        self._keywords_cache = {
            "itinerary": {"positive": {"规划": 0.65, "行程": 0.65, "路线": 0.65}},
            "query": {"positive": {"天气": 0.65, "门票": 0.65, "价格": 0.65}},
            "chat": {"positive": {"你好": 0.4, "谢谢": 0.3}},
            "hotel": {"positive": {"酒店": 0.6, "住宿": 0.6}},
            "food": {"positive": {"美食": 0.65, "小吃": 0.65}},
            "budget": {"positive": {"预算": 0.65, "多少钱": 0.65}},
            "transport": {"positive": {"交通": 0.65, "怎么去": 0.45}},
            "image": {"positive": {"图片": 0.5, "照片": 0.5}},
        }
        self._patterns_cache = {}
        self._loaded = True

        logger.info("[KeywordsLoader] 已加载默认配置")

    def get_keywords(self, intent: str) -> Dict[str, float]:
        """获取指定意图的关键词配置.

        Args:
            intent: 意图标识

        Returns:
            关键词字典（包含 positive 和 negative）
        """
        if self._should_reload():
            self._load_config()

        intent_config = self._keywords_cache.get(intent, {})

        # 返回合并后的关键词（向后兼容旧格式）
        if "positive" in intent_config:
            return intent_config
        else:
            # 旧格式：直接是 {keyword: weight}
            return {"positive": intent_config, "negative": {}}

    def get_patterns(self, intent: str) -> List[str]:
        """获取指定意图的正则模式.

        Args:
            intent: 意图标识

        Returns:
            正则模式列表
        """
        if self._should_reload():
            self._load_config()

        return self._patterns_cache.get(intent, [])

    def get_all_keywords(self) -> Dict[str, Dict[str, Any]]:
        """获取所有意图的关键词配置.

        Returns:
            所有意图关键词配置字典
        """
        if self._should_reload():
            self._load_config()

        # 转换为向后兼容格式
        result = {}
        for intent, config in self._keywords_cache.items():
            if "positive" in config:
                # 新格式：合并 positive 和 negative
                merged = {}
                merged.update(config.get("positive", {}))
                merged.update(config.get("negative", {}))
                result[intent] = merged
            else:
                # 旧格式
                result[intent] = config

        return result

    def get_all_patterns(self) -> Dict[str, List[str]]:
        """获取所有意图的正则模式.

        Returns:
            所有意图模式配置字典
        """
        if self._should_reload():
            self._load_config()

        return self._patterns_cache.copy()

    def get_positive_keywords(self, intent: str) -> Dict[str, float]:
        """获取指定意图的正向关键词.

        Args:
            intent: 意图标识

        Returns:
            正向关键词字典
        """
        keywords = self.get_keywords(intent)
        return keywords.get("positive", keywords if "positive" not in keywords else {})

    def get_negative_keywords(self, intent: str) -> Dict[str, float]:
        """获取指定意图的负向关键词（排除规则）.

        Args:
            intent: 意图标识

        Returns:
            负向关键词字典
        """
        keywords = self.get_keywords(intent)
        return keywords.get("negative", {})

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        return {
            "config_path": str(self.config_path),
            "last_mtime": datetime.fromtimestamp(self._last_mtime).isoformat() if self._last_mtime else None,
            "keywords_count": len(self._keywords_cache),
            "patterns_count": len(self._patterns_cache),
            "loaded": self._loaded,
        }

    def clear_cache(self) -> None:
        """清空所有缓存（用于测试或强制刷新）."""
        self._keywords_cache.clear()
        self._patterns_cache.clear()
        self._last_mtime = 0
        self._loaded = False
        logger.info("[KeywordsLoader] 缓存已清空")

    def force_reload(self) -> Dict[str, Any]:
        """强制重载配置.

        Returns:
            重载后的配置统���信息
        """
        self._loaded = False
        self._last_mtime = 0
        self._load_config()

        return self.get_cache_stats()


# 全局单例实例
_global_loader: KeywordsLoader | None = None


def get_keywords_loader() -> KeywordsLoader:
    """获取全局 KeywordsLoader 实例.

    Returns:
        KeywordsLoader 单例实例
    """
    global _global_loader
    if _global_loader is None:
        _global_loader = KeywordsLoader()
    return _global_loader


def reset_keywords_loader() -> None:
    """重置全局 KeywordsLoader 实例（用于测试）."""
    global _global_loader
    if _global_loader is not None:
        _global_loader.clear_cache()
    _global_loader = None