"""输出格式化器

将LLM的markdown输出转换为更清晰的结构化纯文本。
去掉markdown符号，但保持内容结构。
"""

import re
import logging
from typing import List

logger = logging.getLogger(__name__)


class OutputFormatter:
    """输出格式化器 - 将markdown转换为结构化纯文本"""

    # 符号映射表 - 将emoji转为文本标记
    SYMBOL_MAP = {
        '🍜': '[美食]',
        '🏯': '[景点]',
        '🌳': '[自然]',
        '🏙️': '[都市]',
        '🌆': '[城市]',
        '📅': '[日期]',
        '💰': '[价格]',
        '⭐': '[推荐]',
        '✅': '[完成]',
        '❌': '[错误]',
        '⚠️': '[注意]',
        '💡': '[提示]',
        '📍': '[位置]',
        '🚇': '[地铁]',
        '🚌': '[公交]',
        '🚕': '[出租]',
        '🍽️': '[餐厅]',
        '🍵': '[茶点]',
        '🐦': '[特色]',
        '🏨': '[酒店]',
        '🔥': '[热门]',
        '🎯': '[目标]',
        '📝': '[说明]',
        '🏃': '[活动]',
        '🛍️': '[购物]',
        '🎭': '[文化]',
        '🌸': '[��花]',
        '🎆': '[夜景]',
        '🎡': '[游乐]',
        '🏖️': '[海滩]',
        '🏔️': '[登山]',
        '🏛️': '[博物馆]',
        '🎪': '[表演]',
        '🚢': '[游船]',
    }

    @classmethod
    def format_chunk(cls, chunk: str, is_final: bool = False) -> str:
        """格式化单个输出块

        Args:
            chunk: 原始markdown文本
            is_final: 是否是最终输出(可以跨块处理)

        Returns:
            格式化后的纯文本
        """
        if not chunk:
            return chunk

        # 实时流式输出时，只做简单清理
        if not is_final:
            return cls._clean_inline_markdown(chunk)

        # 最终输出时，做完整的格式转换
        return cls._format_complete_text(chunk)

    @classmethod
    def _clean_inline_markdown(cls, text: str) -> str:
        """清理行内markdown符号(用于流式输出)

        只处理明显的符号，保持文本流畅
        """
        # 先替换emoji为文本（避免emoji中的*被误处理）
        for emoji, symbol in cls.SYMBOL_MAP.items():
            text = text.replace(emoji, symbol)

        # 去掉加粗符号(但保留文字)
        text = text.replace('**', '').replace('__', '')

        # 去掉剩余的单个斜体符号
        text = text.replace('*', '').replace('_', '')

        return text

    @classmethod
    def _format_complete_text(cls, text: str) -> str:
        """格式化完整文本(用于最终输出)

        将markdown结构转换为清晰的纯文本结构
        """
        lines = text.split('\n')
        formatted_lines = []

        for line in lines:
            formatted_line = cls._format_line(line)
            formatted_lines.append(formatted_line)

        return '\n'.join(formatted_lines)

    @classmethod
    def _format_line(cls, line: str) -> str:
        """格式化单行文本

        Args:
            line: 原始行

        Returns:
            格式化后的行
        """
        stripped = line.strip()

        # 空行直接返回
        if not stripped:
            return line

        # 处理标题 (# ## ### 等)
        if stripped.startswith('#'):
            return cls._format_header(stripped)

        # 处理无序列表 (- * +)
        if stripped.startswith(('-', '*', '+')) and len(stripped) > 1 and stripped[1] in (' ', '\t'):
            return cls._format_list_item(stripped)

        # 处理有序列表
        if re.match(r'^\d+[\.\)]\s', stripped):
            return cls._format_numbered_item(stripped)

        # 处理表格行
        if '|' in stripped:
            return cls._format_table_line(stripped)

        # 处理分隔线
        if re.match(r'^[-*_]{3,}$', stripped):
            return '─' * 40

        # 处理引用行
        if stripped.startswith('>'):
            return f"  {stripped[1:].strip()}"

        # 普通文本 - 清理markdown符号
        return cls._format_normal_text(stripped)

    @classmethod
    def _format_header(cls, line: str) -> str:
        """格式化标题行"""
        # 计算标题级别
        level = 0
        for char in line:
            if char == '#':
                level += 1
            else:
                break

        # 提取标题文本
        text = line[level:].strip()

        # 清理文本中的markdown符号
        text = cls._clean_inline_markdown(text)

        # 根据级别选择前缀符号
        prefixes = {
            1: '▓',
            2: '▒',
            3: '░',
            4: '├─',
            5: '├─',
            6: '├─',
        }

        prefix = prefixes.get(level, '░')

        # 添加装饰
        if level <= 2:
            return f"\n{prefix} 【{text}】"
        else:
            return f"{prefix} {text}"

    @classmethod
    def _format_list_item(cls, line: str) -> str:
        """格式化列表项"""
        # 去掉列表符号
        text = re.sub(r'^[-*+]\s+', '', line).strip()

        # 清理markdown符号
        text = cls._clean_inline_markdown(text)

        # 使用简洁的列表符号
        return f"  • {text}"

    @classmethod
    def _format_numbered_item(cls, line: str) -> str:
        """格式化有序列表项"""
        # 提取数字和文本
        match = re.match(r'^(\d+)[\.\)]\s+(.*)', line)
        if match:
            num, text = match.groups()
            text = cls._clean_inline_markdown(text)
            return f"  {num}. {text}"

        return line

    @classmethod
    def _format_table_line(cls, line: str) -> str:
        """格式化表格行"""
        cells = [cell.strip() for cell in line.split('|')]

        # 去掉空的首尾单元格
        if cells and not cells[0]:
            cells.pop(0)
        if cells and not cells[-1]:
            cells.pop()

        # 清理每个单元格
        cleaned_cells = []
        for cell in cells:
            # 跳过分隔线行
            if re.match(r'^[-:\s]+$', cell):
                return ''
            if not cell:  # 跳过空单元格
                continue
            cleaned = cls._clean_inline_markdown(cell)
            cleaned_cells.append(cleaned)

        # 如果没有有效单元格，返回空
        if not cleaned_cells:
            return ''

        # 格式化为键值对形式
        if len(cleaned_cells) == 2:
            return f"  {cleaned_cells[0]}: {cleaned_cells[1]}"
        elif len(cleaned_cells) > 2:
            # 多列表格 - 简化为多行键值对
            lines = []
            for i in range(0, len(cleaned_cells) - 1, 2):
                if i + 1 < len(cleaned_cells):
                    lines.append(f"  {cleaned_cells[i]}: {cleaned_cells[i + 1]}")
                else:
                    lines.append(f"  {cleaned_cells[i]}:")
            return '\n'.join(lines)

        return f"  {cleaned_cells[0]}:"

    @classmethod
    def _format_normal_text(cls, line: str) -> str:
        """格式化普通文本"""
        # 清理markdown符号但保留文本
        text = cls._clean_inline_markdown(line)

        # 处理代码块标记
        if text.strip() in ('```', '----', '***'):
            return '─' * 40

        return text

    @classmethod
    def format_streaming(cls, chunks: List[str]) -> str:
        """批量格式化多个块

        Args:
            chunks: 文本块列表

        Returns:
            合并并格式化后的文本
        """
        full_text = ''.join(chunks)
        return cls._format_complete_text(full_text)


# 便捷函数
def format_output(text: str, is_final: bool = False) -> str:
    """格式化输出文本

    Args:
        text: 原始文本
        is_final: 是否是最终输出

    Returns:
        格式化后的文本
    """
    return OutputFormatter.format_chunk(text, is_final=is_final)
