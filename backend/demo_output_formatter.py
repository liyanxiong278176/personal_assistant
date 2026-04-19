"""演示输出格式化器的效果

对比markdown原始输出和格式化后的输出
"""

import sys
import io

# 设置UTF-8编码以支持emoji和特殊字符
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.output_formatter import OutputFormatter

# 示例：LLM关于广州旅游的原始markdown输出
markdown_output = """欢迎您来广州！作为中国南方的重要城市，广州有着丰富的历史文化。

## 🌆 广州旅游全攻略

### 一、必游景点推荐

**🏯 历史文化类**
1. **陈家祠** - 岭南建筑艺术的瑰宝
2. **沙面岛** - 欧陆风情建筑群，适合拍照

**🌳 自然风光类**
- **白云山** - 广州"市肺"，可俯瞰全城
- **越秀公园** - 内有五羊石像

### 二、美食推荐

| 餐厅名称 | 地址 | 人均 |
|---------|------|------|
| 广州酒家 | 文明南路2号 | ¥80 |
| 陶陶居 | 第十甫路 | ¥100 |

**💡 用餐建议**：记得提前预约
"""

print("=" * 60)
print("原始 Markdown 输出：")
print("=" * 60)
print(markdown_output)

print("\n" + "=" * 60)
print("格式化后的结构化纯文本输出：")
print("=" * 60)

formatted = OutputFormatter._format_complete_text(markdown_output)
print(formatted)

print("\n" + "=" * 60)
print("流式输出（逐字符清理）：")
print("=" * 60)

# 模拟流式输出
chunks = ["**欢迎**", "来到", "*广州*", "！"]
for chunk in chunks:
    formatted_chunk = OutputFormatter.format_chunk(chunk, is_final=False)
    print(f"原始: {chunk:15s} -> 格式化: {formatted_chunk}")

print("\n✅ 格式化器演示完成！")
print("\n主要改进：")
print("1. 去除了所有markdown符号（#, *, **, -, |）")
print("2. Emoji转换为文本标记（🍜 -> [美食]）")
print("3. 标题使用装饰符号（▓, ▒, ░）")
print("4. 列表使用简洁的 • 符号")
print("5. 表格转换为键值对格式")
print("6. 保持了清晰的结构层次")
