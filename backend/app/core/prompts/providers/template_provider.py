"""TemplateProvider - 内存模板提供者

基于 IPromptProvider 接口，在内存中存储和提供提示词模板。
"""

from datetime import datetime
from typing import Dict

from app.core.prompts.providers.base import IPromptProvider, PromptTemplate

# 默认提示词模板（中文）
DEFAULT_TEMPLATES: Dict[str, str] = {
    "itinerary": "你是专业的旅游规划助手。请根据以下信息为用户规划行程：\n"
    "目的地：{destination}\n"
    "天数：{days}天\n"
    "出行人数：{travelers}人\n"
    "预算范围：{budget}\n"
    "用户偏好：{preferences}\n\n"
    "请提供详细的行程安排，包括每日的景点、活动、餐饮和交通建议。",
    "query": "你是专业的旅游查询助手。用户问题：{user_message}\n\n"
    "请根据用户的问题，提供准确、实用的回答。",
    "chat": "你是友好的旅游助手，与用户进行轻松对话。"
    "你可以帮助用户解答旅游相关的问题，分享旅行经验，"
    "并根据对话上下文提供个性化的建议。",
}


class TemplateProvider(IPromptProvider):
    """内存提示词模板提供者

    在内存中存储模板，支持模板的查询、更新和列表操作。
    未找到的意图会回退到 'chat' 模板。

    Example:
        provider = TemplateProvider()
        template = await provider.get_template("itinerary")
        await provider.update_template("itinerary", "新的行程模板...")
        intents = await provider.list_templates()
    """

    def __init__(self, templates: Dict[str, str] = None):
        """初始化模板提供者

        Args:
            templates: 可选的额外模板字典，会与 DEFAULT_TEMPLATES 合并。
                      如果传入的模板键与默认模板重复，以传入的为准。
        """
        # 从默认模板深拷贝一份作为初始状态
        self._templates: Dict[str, str] = dict(DEFAULT_TEMPLATES)
        # 合并用户传入的模板
        if templates:
            self._templates.update(templates)
        # 版本记录：intent -> version string
        self._versions: Dict[str, str] = {}

    async def get_template(self, intent: str, version: str = "latest") -> PromptTemplate:
        """获取指定意图的提示词模板

        如果意图不存在，回退到 'chat' 模板。

        Args:
            intent: 意图标识符
            version: 模板版本（当前保留，语义版本控制）

        Returns:
            PromptTemplate: 提示词模板对象

        Raises:
            KeyError: 当意图和回退模板都不存在时抛出（理论上不会发生）
        """
        # 尝试获取模板，不存在则回退到 chat
        template_str = self._templates.get(intent, self._templates["chat"])
        target_intent = intent if intent in self._templates else "chat"

        # 确定版本号
        version_str = self._versions.get(target_intent, "latest")

        return PromptTemplate(
            intent=target_intent,
            version=version_str,
            template=template_str,
        )

    async def update_template(self, intent: str, template: str) -> str:
        """更新指定意图的提示词模板

        如果版本不存在则创建新版本，返回新版本号。

        Args:
            intent: 意图标识符
            template: 新的模板内容

        Returns:
            str: 新创建的版本号，格式为 "YYYYMMDD.N"
        """
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")

        if intent not in self._versions:
            # 首次创建
            new_version = f"{date_str}.1"
        else:
            last_version = self._versions[intent]
            # 解析日期部分，如果与今天相同则递增子版本号
            if "." in last_version:
                last_date_part = last_version.rsplit(".", 1)[0]
                if last_date_part == date_str:
                    sub_version = int(last_version.rsplit(".", 1)[1])
                    new_version = f"{date_str}.{sub_version + 1}"
                else:
                    new_version = f"{date_str}.1"
            else:
                new_version = f"{date_str}.1"

        self._templates[intent] = template
        self._versions[intent] = new_version
        return new_version

    async def list_templates(self) -> list:
        """列出所有可用的意图模板

        Returns:
            List[str]: 所有意图标识符列表
        """
        return list(self._templates.keys())
