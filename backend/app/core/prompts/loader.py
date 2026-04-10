"""PromptConfigLoader - YAML-based hot-reload configuration loader.

Supports:
- File modification time detection for auto-reload
- Intent-to-template mapping
- Memory caching with TTL
- Graceful fallback on errors
"""

import logging
import yaml
from pathlib import Path
from typing import Any, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptConfigLoader:
    """提示词配置加载器 - 支持热更新.

    功能特性:
    1. 检测配置文件修改时间，自动重载
    2. 内存缓存配置，减少文件 I/O
    3. 支持意图到模板的动态映射
    """

    def __init__(self, config_path: str | None = None):
        """初始化配置加载器.

        Args:
            config_path: prompts.yaml 配置文件路径
        """
        if config_path is None:
            # 默认路径
            backend_dir = Path(__file__).parent.parent
            config_path = backend_dir / "prompts/config/prompts.yaml"

        self.config_path = Path(config_path)
        self._cache: Dict[str, Any] | None = None
        self._last_mtime: float = 0
        self._template_cache: Dict[str, str] = {}
        self._template_cache_time: Dict[str, float] = {}
        self._cache_ttl: int = 60  # 模板缓存60秒

        logger.info(f"[PromptLoader] 初始化，配置路径: {self.config_path}")

    def _should_reload_config(self) -> bool:
        """检查配置文件是否被修改.

        Returns:
            True if file was modified since last load
        """
        if not self.config_path.exists():
            logger.warning(f"[PromptLoader] 配置文件不存在: {self.config_path}")
            return False

        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._last_mtime

    def _should_reload_template(self, template_path: Path) -> bool:
        """检查模板文件是否被修改.

        Args:
            template_path: 模板文件路径

        Returns:
            True if file was modified since last load
        """
        if not template_path.exists():
            return False

        current_mtime = template_path.stat().st_mtime
        cached_time = self._template_cache_time.get(str(template_path), 0)

        # 修复：直接比较 mtime，不计算差值
        return cached_time == 0 or current_mtime > cached_time

    def _load_config(self) -> Dict[str, Any]:
        """从 YAML 文件加载配置.

        Returns:
            配置字典
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self._last_mtime = self.config_path.stat().st_mtime
            logger.info(f"[PromptLoader] 配置已加载: {len(config.get('mapping', {}))} 个意图")
            return config
        except FileNotFoundError:
            logger.error(f"[PromptLoader] 配置文件不存在: {self.config_path}")
            return self._get_default_config()
        except yaml.YAMLError as e:
            logger.error(f"[PromptLoader] YAML 解析失败: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（降级方案）."""
        return {
            "mapping": {
                "itinerary": {"template": "templates/itinerary.md", "enabled": True},
                "query": {"template": "templates/query.md", "enabled": True},
                "chat": {"template": "templates/chat.md", "enabled": True},
                "image": {"template": "templates/image.md", "enabled": True},
                "hotel": {"template": "templates/hotel.md", "enabled": True},
                "food": {"template": "templates/food.md", "enabled": True},
                "budget": {"template": "templates/budget.md", "enabled": True},
                "transport": {"template": "templates/transport.md", "enabled": True},
            },
            "settings": {"watch_interval": 1, "cache_ttl": 60}
        }

    def _load_template(self, template_path: Path) -> str:
        """加载模板文件内容.

        Args:
            template_path: 模板文件路径

        Returns:
            模板内容字符串
        """
        try:
            content = template_path.read_text(encoding="utf-8")
            mtime = template_path.stat().st_mtime
            template_key = str(template_path)

            # 修复：正确写入缓存
            self._template_cache[template_key] = content
            self._template_cache_time[template_key] = mtime

            logger.debug(f"[PromptLoader] 模板已加载: {template_path.name}")
            return content
        except FileNotFoundError:
            logger.warning(f"[PromptLoader] 模板文件不存在: {template_path}")
            return self._get_default_template(template_path.stem)

    def _get_default_template(self, intent: str) -> str:
        """获取默认模板（降级方案）."""
        defaults = {
            "itinerary": "# 行程规划助手\n\n你是一个专业的旅游规划助手...",
            "query": "# 信息查询助手\n\n请帮助用户查询具体信息...",
            "chat": "# 对话助手\n\n你是一个友好、专业的 AI 助手...",
            "image": "# 图片识别助手\n\n请识别图片中的内容...",
            "hotel": "# 酒店推荐助手\n\n你是一个酒店推荐专家...",
            "food": "# 美食推荐助手\n\n你是一个美食推荐专家...",
            "budget": "# 预算规划助手\n\n你是一个预算规划专家...",
            "transport": "# 交通出行助手\n\n你是一个交通出行专家...",
        }
        return defaults.get(intent, "# 助手\n\n你是一个 AI 助手。")

    def get_config(self) -> Dict[str, Any]:
        """获取配置（自动检测更新）."""
        if self._should_reload_config():
            self._cache = self._load_config()

        return self._cache or self._get_default_config()

    def get_template(self, intent: str) -> str:
        """获取意图对应的模板内容.

        Args:
            intent: 意图标识

        Returns:
            模板内容字符串
        """
        config = self.get_config()
        mapping = config.get("mapping", {})
        intent_config = mapping.get(intent)

        # 检查意图是否启用
        if not intent_config or not intent_config.get("enabled", True):
            logger.debug(f"[PromptLoader] 意图 '{intent}' 未启用，使用默认模板")
            return self._get_default_template(intent)

        # 获取模板路径
        template_name = intent_config.get("template", f"templates/{intent}.md")
        # config路径是 prompts/config/prompts.yaml，templates在 prompts/templates/
        templates_dir = self.config_path.parent.parent
        template_path = templates_dir / template_name

        # 检查模板文件是否需要重载
        if self._should_reload_template(template_path):
            return self._load_template(template_path)

        # 从缓存返回
        template_key = str(template_path)
        return self._template_cache.get(template_key, "")

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        return {
            "config_last_mtime": datetime.fromtimestamp(self._last_mtime).isoformat() if self._last_mtime else None,
            "template_cache_size": len(self._template_cache),
            "template_cached": list(self._template_cache.keys()),
        }

    def clear_cache(self) -> None:
        """清空所有缓存（用于测试或强制刷新）."""
        self._cache = None
        self._last_mtime = 0
        self._template_cache.clear()
        self._template_cache_time.clear()
        logger.info("[PromptLoader] 缓存已清空")
