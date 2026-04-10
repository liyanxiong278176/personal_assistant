# 意图识别系统增强设计文档

**设计目标**: 解决高频查询覆盖率未达标、提示词热更新未实现、意图-模板动态映射未落地三大问题

**设计日期**: 2026-04-10

---

## 一、当前系统分析

### 1.1 存在的问题

| 问题 | 现状 | 影响 |
|------|------|------|
| 意图类型偏少 | 仅 4 种 (itinerary, query, chat, image) | 高频查询覆盖率仅 75%，未达标 |
| 关键词覆盖不足 | 缺少 hotel、food、budget、transport 等关键词 | 用户查询需调用 LLM，响应慢 |
| 提示词硬编码 | DEFAULT_SYSTEM_PROMPT 硬编码在代码中 | 修改需重启服务 |
| 无热更新机制 | 无文件监听和自动重载 | 维护成本高，迭代慢 |
| 意图-模板映射未落地 | PromptService 存在但未被 QueryEngine 使用 | 无法实现动态模板选择 |

### 1.2 目标指标

| 指标 | 当前��� | 目标值 |
|------|--------|--------|
| 意图类型数量 | 4 种 | 6-8 种 |
| 高频查询覆盖率 | ~75% | ≥80% |
| 提示词热更新 | ❌ 不支持 | ✅ 支持 YAML 配置文件热更新 |
| 意图-模板映射 | ❌ 未使用 | ✅ 动态映射 |

---

## 二、设计方案

### 2.1 意图类型扩展

#### 新增意图类型

| 意图类型 | 英文标识 | 优先级 | 关键词定义 |
|---------|---------|--------|------------|
| 行程规划 | `itinerary` | 10 | 规划(0.3), 行程(0.3), 路线(0.3), 旅游(0.2), 旅行(0.2), 几天(0.2), 日游(0.2) |
| 信息查询 | `query` | 10 | 天气(0.3), 温度(0.3), 门票(0.3), 价格(0.3), 怎么去(0.2), 交通(0.2), 开放时间(0.2) |
| 普通对话 | `chat` | 100 | 你好(0.2), 在吗(0.2), 您好(0.2), 谢谢(0.1), 哈哈(0.1), 帮忙(0.1) |
| 图片识别 | `image` | 5 | 图片(0.3), 照片(0.3), 识别(0.3) |
| 酒店预订 | `hotel` | 10 | 酒店(0.3), 住宿(0.3), 民宿(0.2), 宾馆(0.2), 住(0.1), 房间(0.1) |
| 美食推荐 | `food` | 10 | 美食(0.3), 小吃(0.3), 餐厅(0.2), 菜(0.2), 吃(0.1), 好吃(0.1) |
| 预算规划 | `budget` | 10 | 预算(0.3), 多少钱(0.3), 花费(0.2), 便宜(0.2), 贵(0.2), 价位(0.1) |
| 交通出行 | `transport` | 10 | 怎么去(0.3), 交通(0.3), 飞机(0.2), 高铁(0.2), 开车(0.2), 自驾(0.2) |

#### 实现文件结构

```
backend/app/core/intent/
├── keywords.py              # 统一的关键词定义
├── strategies/
│   └── rule.py             # 更新 RuleStrategy 使用新关键词
└── config/
    └── intent_config.yaml  # 意图配置（可选，用于扩展）
```

---

### 2.2 提示词热更新系统

#### 配置文件结构

```
backend/app/core/prompts/
├── config/
│   └── prompts.yaml          # 主配置文件
├── templates/              # 意图模板目录
│   ├── system.md           # 通用系统提示词
│   ├── itinerary.md        # 行程规划模板
│   ├── query.md            # 信息查询模板
│   ├── chat.md             # 普通对话模板
│   ├── image.md            # 图片识别模板
│   ├── hotel.md            # 酒店预订模板
│   ├── food.md             # 美食推荐模板
│   ├── budget.md           # 预算规划模板
│   └── transport.md        # 交通出行模板
└── loader.py               # 配置加载器（支持热更新）
```

#### prompts.yaml 配置格式

```yaml
# 意图与模板映射关系
mapping:
  itinerary:
    template: templates/itinerary.md
    enabled: true
    priority: 10
    cache_ttl: 300  # 缓存5分钟
    
  query:
    template: templates/query.md
    enabled: true
    priority: 10
    cache_ttl: 300
    
  chat:
    template: templates/chat.md
    enabled: true
    priority: 100
    cache_ttl: 60
    
  image:
    template: templates/image.md
    enabled: true
    priority: 5
    cache_ttl: 600
    
  hotel:
    template: templates/hotel.md
    enabled: true
    priority: 10
    cache_ttl: 300
    
  food:
    template: templates/food.md
    enabled: true
    priority: 10
    cache_ttl: 300
    
  budget:
    template: templates/budget.md
    enabled: true
    priority: 10
    cache_ttl: 300
    
  transport:
    template: templates/transport.md
    enabled: true
    priority: 10
    cache_ttl: 300

# 全局配置
settings:
  # 文件监听间隔（秒）
  watch_interval: 1
  # 模板缓存过期时间（秒）
  cache_ttl: 60
```

#### 热更新机制实现

```python
# backend/app/core/prompts/loader.py

import logging
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptConfigLoader:
    """提示词配置加载器 - 支持热更新
    
    功能特性:
    1. 检测配置文件修改时间，自动重载
    2. 内存缓存配置，减少文件 I/O
    3. 支持意图到模板的动态映射
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化配置加载器
        
        Args:
            config_path: prompts.yaml 配置文件路径
        """
        if config_path is None:
            # 默认路径
            backend_dir = Path(__file__).parent.parent
            config_path = backend_dir / "prompts/config/prompts.yaml"
        
        self.config_path = Path(config_path)
        self._cache: Optional[Dict[str, Any]] = None
        self._last_mtime: float = 0
        self._template_cache: Dict[str, str] = {}
        self._template_cache_time: Dict[str, float] = {}
        self._cache_ttl: int = 60  # 模板缓存60秒
        
        logger.info(f"[PromptLoader] 初始化，配置路径: {self.config_path}")
    
    def _should_reload_config(self) -> bool:
        """检查配置文件是否被修改
        
        Returns:
            True if file was modified since last load
        """
        if not self.config_path.exists():
            logger.warning(f"[PromptLoader] 配置文件不存在: {self.config_path}")
            return False
        
        current_mtime = self.config_path.stat().st_mtime
        return current_mtime > self._last_mtime
    
    def _should_reload_template(self, template_path: Path) -> bool:
        """检查模板文件是否被修改
        
        Args:
            template_path: 模板文件路径
            
        Returns:
            True if file was modified since last load
        """
        if not template_path.exists():
            return False
        
        current_mtime = template_path.stat().st_mtime
        cached_time = self._template_cache_time.get(str(template_path), 0)
        
        # 检查缓存是否过期
        cache_age = current_mtime - cached_time
        return cache_age > self._cache_ttl
    
    def _load_config(self) -> Dict[str, Any]:
        """从 YAML 文件加载配置
        
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
            return {"mapping": {}, "settings": {"watch_interval": 1}}
        except yaml.YAMLError as e:
            logger.error(f"[PromptLoader] YAML 解析失败: {e}")
            return {"mapping": {}, "settings": {"watch_interval": 1}}
    
    def _load_template(self, template_path: Path) -> str:
        """加载模板文件内容
        
        Args:
            template_path: 模板文件路径
            
        Returns:
            模板内容字符串
        """
        try:
            content = template_path.read_text(encoding="utf-8")
            self._template_cache_time[str(template_path)] = template_path.stat().st_mtime
            logger.debug(f"[PromptLoader] 模板已加载: {template_path.name}")
            return content
        except FileNotFoundError:
            logger.warning(f"[PromptLoader] 模板文件不存在: {template_path}")
            return self._get_default_template(template_path.stem)
    
    def _get_default_template(self, intent: str) -> str:
        """获取默认模板（降级方案）"""
        defaults = {
            "itinerary": "# 行程规划助手\n\n你是一个专业的旅游规划助手...",
            "query": "# 信息查询助手\n\n请帮助用户查询具体信息...",
            "chat": "# 对话助手\n\n你是一个友好、专业的 AI 助手...",
            "hotel": "# 酒店推荐助手\n\n你是一个酒店推荐专家...",
            "food": "# 美食推荐助手\n\n你是一个美食推荐专家...",
            "budget": "# 预算规划助手\n\n你是一个预算规划专家...",
            "transport": "# 交通出行助手\n\n你是一个交通出行专家...",
        }
        return defaults.get(intent, "# 助手\n\n你是一个 AI 助手。")
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置（自动检测更新）"""
        if self._should_reload_config():
            self._cache = self._load_config()
        
        return self._cache or {"mapping": {}, "settings": {}}
    
    def get_template(self, intent: str) -> str:
        """获取意图对应的模板内容
        
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
        templates_dir = self.config_path.parent
        template_path = templates_dir / template_name
        
        # 检查模板文件是否需要重载
        if self._should_reload_template(template_path):
            return self._load_template(template_path)
        
        # 从缓存返回
        return self._template_cache.get(str(template_path), "")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "config_last_mtime": datetime.fromtimestamp(self._last_mtime).isoformat() if self._last_mtime else None,
            "template_cache_size": len(self._template_cache),
            "template_cached": list(self._template_cache.keys()),
        }
    
    def clear_cache(self) -> None:
        """清空所有缓存（用于测试或强制刷新）"""
        self._cache = None
        self._last_mtime = 0
        self._template_cache.clear()
        self._template_cache_time.clear()
        logger.info("[PromptLoader] 缓存已清空")
```

---

### 2.3 意图-模板动态映射

#### 集成到 QueryEngine

```python
# backend/app/core/query_engine.py (修改部分)

from app.core.prompts.loader import PromptConfigLoader

class QueryEngine:
    def __init__(self, ...):
        # ... 现有初始化 ...
        
        # 新增：提示词配置加载器
        self._prompt_loader = PromptConfigLoader()
        
        # 修改：使用 PromptService 而不是 PromptBuilder
        from app.core.prompts.service import PromptService
        from app.core.prompts.providers.template_provider import TemplateProvider
        
        self._prompt_service = PromptService(
            provider=TemplateProvider(loader=self._prompt_loader)
        )
        
        logger.info("[QueryEngine] 提示词服务已初始化（支持热更新）")
    
    async def _build_prompt(
        self,
        user_id: Optional[str],
        tool_results: Dict[str, Any],
        slots,
        intent: str,
        conversation_id: Optional[str] = None,
        user_input: Optional[str] = None,
    ) -> str:
        """构建上下文 - 使用意图动态模板"""
        
        # 构建 RequestContext
        from app.core.context import RequestContext
        context = RequestContext(
            message=user_input or "",
            user_id=user_id,
            conversation_id=conversation_id,
            slots=slots,
            tool_results=tool_results,
            memories=self._get_memories(conversation_id, user_id),
            intent=intent
        )
        
        # 使用 PromptService 渲染意图对应的模板
        try:
            prompt = await self._prompt_service.render(intent, context)
            return prompt
        except Exception as e:
            logger.warning(f"[QueryEngine] 模板渲染失败，使用默认: {e}")
            # 降级到默认提示词
            return self.get_system_prompt()
```

---

## 三、实施计划

### 阶段 1: 意图类型扩展 (1-2天)

**任务列表**:
1. 创建 `keywords.py` 统一关键词定义
2. 更新 `rule.py` 使用新关键词
3. 更新 LLM 提示词模板支持新意图
4. 单元测试验证每种意图的分类准确率

**文件修改**:
- 新建: `backend/app/core/intent/keywords.py`
- 修改: `backend/app/core/intent/strategies/rule.py`
- 修改: `backend/app/core/intent/strategies/llm_fallback.py`

### 阶段 2: 提示词热更新系统 (2-3天)

**任务列表**:
1. 创建配置目录结构
2. 创建 `prompts.yaml` 配置文件
3. 创建 8 个意图模板文件
4. 实现 `loader.py` 热更新加载器
5. 更新 `PromptService` 使用新加载器
6. 集成测试文件修改自动重载

**文件修改**:
- 新建: `backend/app/core/prompts/config/prompts.yaml`
- 新建: `backend/app/core/prompts/templates/*.md` (8个文件)
- 新建: `backend/app/core/prompts/loader.py`
- 修改: `backend/app/core/prompts/service.py`

### 阶段 3: 意图-模板动态映射 (1-2天)

**任务列表**:
1. 修改 `QueryEngine` 使用 `PromptService`
2. 移除旧的 `PromptBuilder` 依赖
3. 端到端测试验证意图-模板映射
4. 性能测试确保缓存机制正常工作

**文件修改**:
- 修改: `backend/app/core/query_engine.py`
- 修改: `backend/app/core/prompts/__init__.py`

### 阶段 4: 测试与验证 (1-2天)

**测试任务**:
1. 单元测试: 关键词规则测试
2. 集成测试: 完整意图识别流程测试
3. 热更新测试: 修改配置文件验证自动重载
4. 性能测试: 缓存命中率测试
5. 评估系统更新: 新增意图的评估指标收集

---

## 四、预期效果

### 4.1 功能改进

| 功能项 | 改进效果 |
|--------|----------|
| 意图类型 | 4种 → 8种 |
| 高频查询覆盖率 | 75% → ≥85% |
| 提示词热更新 | 不支持 → 支持 YAML 配置热更新 |
| 意图-模板映射 | 未使用 → 完全动态化 |

### 4.2 性能改进

| 指标 | 改进效果 |
|------|----------|
| 简单查询响应速度 | 提升 50%+ (缓存命中) |
| 模板缓存命中率 | ≥80% (60秒缓存) |
| 配置重载延迟 | <1秒 (下次请求时生效) |

### 4.3 维护性改进

- ✅ 提示词模板与代码分离，易于维护
- ✅ 配置文件外部化，无需重启服务即可更新
- ✅ 意图与模板映射关系清晰可配置
- ✅ 新增意图类型只需添加配置和模板文件

---

## 五、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 配置文件格式错误导致系统崩溃 | 中 | YAML 解析失败时使用默认模板，记录错误日志 |
| 文件监听增加系统开销 | 低 | 使用 mtime 检查，开销极小 |
| 缓存一致性问题 | 低 | 设置合理的缓存过期时间 |
| 模板文件丢失 | 中 | 模板文件丢失时降级到默认模板 |

---

**文档版本**: v1.0
**最后更新**: 2026-04-10
**状态**: 待评审
