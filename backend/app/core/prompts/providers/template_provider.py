"""TemplateProvider - 文件模板提供者

从 templates/ 目录加载模板文件，不再使用硬编码模板。
"""

from datetime import datetime
from pathlib import Path
from typing import Dict

from app.core.prompts.providers.base import IPromptProvider, PromptTemplate

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class TemplateProvider(IPromptProvider):
    """文件模板提供者

    从 templates/ 目录按意图加载 .md 模板文件。
    ���退到 chat.md，再回退到硬编码兜底。
    """

    def __init__(self, templates_dir: Path = None):
        self._templates_dir = templates_dir or TEMPLATES_DIR
        self._versions: Dict[str, str] = {}

    async def get_template(self, intent: str, version: str = "latest") -> PromptTemplate:
        """获取指定意图的模板

        查找顺序: templates/{intent}.md → chat.md → 硬编码兜底
        """
        # 尝试加载意图对应的模板文件
        for candidate in [intent, "chat"]:
            file_path = self._templates_dir / f"{candidate}.md"
            try:
                content = file_path.read_text(encoding="utf-8")
                target = candidate
                break
            except FileNotFoundError:
                continue
        else:
            # 兜底
            content = "你是一个专业的旅游助手 AI，请帮助用户。"
            target = intent

        return PromptTemplate(
            intent=target,
            version=self._versions.get(target, "latest"),
            template=content,
        )

    async def update_template(self, intent: str, template: str) -> str:
        """更新模板（写入文件）"""
        now = datetime.now()
        date_str = now.strftime("%Y%m%d")
        if intent not in self._versions:
            new_version = f"{date_str}.1"
        else:
            last_version = self._versions[intent]
            if "." in last_version and last_version.rsplit(".", 1)[0] == date_str:
                sub = int(last_version.rsplit(".", 1)[1])
                new_version = f"{date_str}.{sub + 1}"
            else:
                new_version = f"{date_str}.1"

        file_path = self._templates_dir / f"{intent}.md"
        file_path.write_text(template, encoding="utf-8")
        self._versions[intent] = new_version
        return new_version

    async def list_templates(self) -> list:
        """列出所有可用的意图模板"""
        return [p.stem for p in self._templates_dir.glob("*.md")]
