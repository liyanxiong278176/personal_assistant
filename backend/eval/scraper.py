"""Scrape real travel queries from Ctrip Q&A (you.ctrip.com/asks).

Uses Playwright MCP to extract question titles from public listing pages.
Conservative strategy: 5-8 category pages, 3s delay between pages.

This script is designed to be driven by Claude's Playwright MCP tools.
Run it step by step:
  1. python -m eval.scraper --mode scrape   # Generate page URLs
  2. (Use Playwright MCP to scrape each URL)
  3. python -m eval.scraper --mode merge    # Merge all scraped pages

Usage:
    cd backend
    python -m eval.scraper --mode urls      # List URLs to scrape
    python -m eval.scraper --mode merge     # Merge scraped JSON files
"""

import argparse
import json
import sys
import io
from collections import Counter
from pathlib import Path
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

OUTPUT_DIR = Path(__file__).parent / "scraped_pages"
OUTPUT_DIR.mkdir(exist_ok=True)

# Conservative scrape targets
SCRAPE_URLS = [
    # Global hot questions (pages 1-7 = ~140 questions)
    ("https://you.ctrip.com/asks", "global_hot_p1"),
    ("https://you.ctrip.com/asks/p2", "global_hot_p2"),
    ("https://you.ctrip.com/asks/p3", "global_hot_p3"),
    ("https://you.ctrip.com/asks/p4", "global_hot_p4"),
    ("https://you.ctrip.com/asks/p5", "global_hot_p5"),
    ("https://you.ctrip.com/asks/p6", "global_hot_p6"),
    ("https://you.ctrip.com/asks/p7", "global_hot_p7"),
    # Beijing (pages 1-3 = ~60 questions)
    ("https://you.ctrip.com/asks/beijing1", "beijing_p1"),
    ("https://you.ctrip.com/asks/beijing1/p2", "beijing_p2"),
    ("https://you.ctrip.com/asks/beijing1/p3", "beijing_p3"),
    # Shanghai (pages 1-3 = ~60 questions)
    ("https://you.ctrip.com/asks/shanghai2", "shanghai_p1"),
    ("https://you.ctrip.com/asks/shanghai2/p2", "shanghai_p2"),
    ("https://you.ctrip.com/asks/shanghai2/p3", "shanghai_p3"),
    # Chengdu (pages 1-2 = ~40 questions)
    ("https://you.ctrip.com/asks/chengdu104", "chengdu_p1"),
    ("https://you.ctrip.com/asks/chengdu104/p2", "chengdu_p2"),
    # Hotel tag (pages 1-2 = ~40 questions)
    ("https://you.ctrip.com/asks/t105341", "hotel_tag_p1"),
    ("https://you.ctrip.com/asks/t105341/p2", "hotel_tag_p2"),
    # Latest questions (pages 1-3 = ~60 questions)
    ("https://you.ctrip.com/asks/k1", "latest_p1"),
    ("https://you.ctrip.com/asks/k1/p2", "latest_p2"),
    ("https://you.ctrip.com/asks/k1/p3", "latest_p3"),
    # Hangzhou (pages 1-2 = ~40 questions)
    ("https://you.ctrip.com/asks/hangzhou14", "hangzhou_p1"),
    ("https://you.ctrip.com/asks/hangzhou14/p2", "hangzhou_p2"),
]

# JavaScript to extract questions from a page
EXTRACT_JS = """
() => {
  const questions = [];
  const links = document.querySelectorAll('a[href*="/asks/detail"]');
  links.forEach(link => {
    const h2 = link.querySelector('h2');
    const answerP = link.querySelector('p');
    if (h2) {
      questions.push({
        query: h2.textContent.trim(),
        answers: answerP ? parseInt(answerP.textContent) || 0 : 0,
        url: link.href
      });
    }
  });
  return questions;
}
"""


def list_urls():
    """Print all URLs to scrape."""
    print(f"\n{'='*60}")
    print(f"  携程问答爬取计划 (保守策略)")
    print(f"{'='*60}")
    print(f"\n  总页面数: {len(SCRAPE_URLS)}")
    print(f"  预计获取: {len(SCRAPE_URLS) * 20} 条 (去重后约400-500条)")
    print(f"  预计耗时: ~{len(SCRAPE_URLS) * 3}s (每页3秒延迟)\n")

    for i, (url, name) in enumerate(SCRAPE_URLS, 1):
        print(f"  {i:2d}. [{name:18s}] {url}")

    print(f"\n  提取JS:\n  {EXTRACT_JS.strip()[:80]}...")
    print()


def save_page(name: str, questions: list[dict]) -> None:
    """Save a scraped page's questions to a JSON file."""
    path = OUTPUT_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "source": name,
            "scraped_at": datetime.now().isoformat(),
            "count": len(questions),
            "questions": questions,
        }, f, ensure_ascii=False, indent=2)
    print(f"  Saved {len(questions)} questions to {path}")


def merge_pages() -> None:
    """Merge all scraped page JSON files into raw_queries.json."""
    all_questions = []
    seen_queries = set()

    for path in sorted(OUTPUT_DIR.glob("*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for q in data.get("questions", []):
            # Deduplicate by query text
            normalized = q["query"].strip().lower()
            # Remove hotel name prefix pattern: #xxx酒店#
            import re
            clean_query = re.sub(r'#.*?#', '', q["query"]).strip()
            if not clean_query or len(clean_query) < 3:
                continue
            # Skip non-travel queries (customer service, app issues)
            skip_words = ["客服", "投诉", "电话", "购物车", "订单", "退款", "发货",
                         "携程", "APP", "登录", "注册", "账号", "密码", "会员"]
            if any(w in q["query"] for w in skip_words):
                continue

            key = clean_query.lower()
            if key not in seen_queries:
                seen_queries.add(key)
                all_questions.append({
                    "query": clean_query,
                    "answers": q.get("answers", 0),
                    "url": q.get("url", ""),
                    "source": data["source"],
                })

    output = {
        "source": "ctrip_asks",
        "scraped_at": datetime.now().isoformat(),
        "total_pages": len(list(OUTPUT_DIR.glob("*.json"))),
        "total_queries": len(all_questions),
        "queries": all_questions,
    }

    output_path = Path(__file__).parent / "raw_queries.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print distribution
    print(f"\n{'='*60}")
    print(f"  爬取结果汇总")
    print(f"{'='*60}")
    print(f"  总页面: {output['total_pages']}")
    print(f"  去重后query数: {len(all_questions)}")
    print(f"\n  按来源分布:")
    source_counts = Counter(q["source"] for q in all_questions)
    for source, count in source_counts.most_common():
        print(f"    {source}: {count}")
    print(f"\n  示例query:")
    for q in all_questions[:10]:
        print(f"    [{q['source']:18s}] {q['query'][:50]}")
    print(f"\n  已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Ctrip Q&A scraper helper")
    parser.add_argument("--mode", choices=["urls", "merge", "save"],
                       default="urls", help="Operation mode")
    parser.add_argument("--name", type=str, help="Page name for --mode save")
    parser.add_argument("--data", type=str, help="JSON data for --mode save")
    args = parser.parse_args()

    if args.mode == "urls":
        list_urls()
    elif args.mode == "merge":
        merge_pages()
    elif args.mode == "save":
        if not args.name or not args.data:
            print("Usage: --mode save --name PAGE_NAME --data '[...]'")
            sys.exit(1)
        questions = json.loads(args.data)
        save_page(args.name, questions)


if __name__ == "__main__":
    main()
