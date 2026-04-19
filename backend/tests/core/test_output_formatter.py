"""测试输出格式化器

验证markdown到结构化纯文本的转换
"""

import pytest
from app.core.output_formatter import OutputFormatter, format_output


class TestOutputFormatter:
    """测试输出格式化器"""

    def test_clean_inline_markdown(self):
        """测试行内markdown清理"""
        # 加粗
        assert OutputFormatter._clean_inline_markdown("**粗体**") == "粗体"
        assert OutputFormatter._clean_inline_markdown("__粗体__") == "粗体"

        # 斜体
        assert OutputFormatter._clean_inline_markdown("*斜体*") == "斜体"

        # 混合
        text = "**这是** *粗体* 和斜体"
        result = OutputFormatter._clean_inline_markdown(text)
        assert "**" not in result
        assert "*" not in result

    def test_format_header(self):
        """测试标题格式化"""
        # 一级标题
        assert OutputFormatter._format_header("# 一级标题") == "\n▓ 【一级标题】"

        # 二级标题
        assert OutputFormatter._format_header("## 二级标题") == "\n▒ 【二级标题】"

        # 三级标题
        assert OutputFormatter._format_header("### 三级标题") == "░ 三级标题"

        # 带emoji的标题
        result = OutputFormatter._format_header("## 🍜 美食推荐")
        assert "[美食]" in result
        assert "▒" in result

    def test_format_list_item(self):
        """测试列表项格式化"""
        # 无序列表
        assert OutputFormatter._format_list_item("- 项目一") == "  • 项目一"
        assert OutputFormatter._format_list_item("* 项目二") == "  • 项目二"
        assert OutputFormatter._format_list_item("+ 项目三") == "  • 项目三"

        # 带markdown的列表
        result = OutputFormatter._format_list_item("- **重要** 项目")
        assert "**" not in result
        assert "•" in result

    def test_format_numbered_item(self):
        """测试有序列表格式化"""
        assert OutputFormatter._format_numbered_item("1. 第一项") == "  1. 第一项"
        assert OutputFormatter._format_numbered_item("2) 第二项") == "  2. 第二项"

    def test_format_table_line(self):
        """测试表格行格式化"""
        # 两列表格
        result = OutputFormatter._format_table_line("| **名称** | **值** |")
        assert "名称:" in result
        assert "值" in result  # 值在冒号后
        assert "|" not in result or result.count("|") <= 2  # 可能保留两侧的|

        # 分隔线
        assert OutputFormatter._format_table_line("|---|---|") == ""

    def test_format_complete_text(self):
        """测试完整文本格式化"""
        markdown_text = """# 欢迎来到广州

## 必游景点

- 广州塔 - 地标建筑
- 白云山 - 自然风光
- 陈家祠 - 历史文化

## 美食推荐

| 餐厅 | 地址 |
|------|------|
| 广州酒家 | 文明路 |
| 陶陶居 | 第十甫路 |

**注意事项**：记得带伞
"""

        result = OutputFormatter._format_complete_text(markdown_text)

        # 检查标题转换
        assert "▓ 【欢迎来到广州】" in result
        assert "▒ 【必游景点】" in result

        # 检查列表转换
        assert "• 广州塔" in result
        assert "• 白云山" in result

        # 检查表格转换
        assert "广州酒家:" in result
        assert "文明路" in result

        # 检查加粗被去除
        assert "**" not in result

    def test_streaming_format(self):
        """测试流式格式化"""
        # 流式输出时只做简单清理（使用无空格版本测试紧凑输出）
        chunk = "**这是***粗体*文本"
        result = OutputFormatter.format_chunk(chunk, is_final=False)
        assert "**" not in result
        assert "*" not in result
        assert "这是粗体文本" in result

    def test_emoji_replacement(self):
        """测试emoji替换"""
        text = "🍜 美食 🏯 景点 🌳 自然"
        result = OutputFormatter._clean_inline_markdown(text)
        assert "[美食]" in result
        assert "[景点]" in result
        assert "[自然]" in result
        assert "🍜" not in result

    def test_format_chunk(self):
        """测试format_chunk便捷函数"""
        markdown = "# 标题\n\n- 项目1\n- 项目2"
        result = format_output(markdown, is_final=True)
        assert "▓ 【标题】" in result
        assert "• 项目1" in result
        assert "• 项目2" in result

    def test_real_world_example(self):
        """测试真实世界示例"""
        # 模拟LLM关于广州旅游的输出
        markdown = """欢迎您来广州！作为中国南方的重要城市，广州有着丰富的历史文化、美食和现代都市魅力。

## 🌆 广州旅游全攻略

### 一、必游景点推荐

**🏯 历史文化类**
1. **陈家祠** - 岭南建筑艺术的瑰宝
2. **沙面岛** - 欧陆风情建筑群，适合拍照
3. **石室圣心大教堂** - 全球四座全石结构哥特式教堂之一

**🌳 自然风光类**
- **白云山** - 广州"市肺"，可俯瞰全城
- **越秀公园** - 内有五羊石像（广州城标）

### 二、美食推荐

| 餐厅名称 | 地址 | 人均 |
|---------|------|------|
| 广州酒家 | 文明南路2号 | ¥80 |
| 陶陶居 | 第十甫路 | ¥100 |

**💡 用餐建议**：记得提前预约
"""

        result = OutputFormatter._format_complete_text(markdown)

        # 验证结构保持清晰
        assert "▒" in result and "广州旅游全攻略" in result
        assert "░" in result and "一、必游景点推荐" in result
        assert "欢迎您来广州" in result

        # 验证markdown符号被去除
        assert "**" not in result
        assert "#" not in result.replace("▓", "").replace("▒", "").replace("░", "")

        # 验证列表和表格被转换
        assert "陈家祠" in result
        assert "广州酒家" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
