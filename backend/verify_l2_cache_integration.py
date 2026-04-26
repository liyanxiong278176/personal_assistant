"""验证所有评测脚本都已集成 L2 语义缓存"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_semantic_cache_integration():
    """检查所有测试文件是否包含 SemanticCache 创建代码"""

    files_to_check = [
        "eval/run_eval.py",
        "test_thresholds.py",
        "test_full_eval.py",
    ]

    print("L2 Semantic Cache Integration Check")
    print("=" * 60)

    for filepath in files_to_check:
        full_path = os.path.join(os.path.dirname(__file__), filepath)

        if not os.path.exists(full_path):
            print(f"[MISSING] {filepath} - file not found")
            continue

        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for SemanticCache import and creation
        has_import = "SemanticCache" in content
        has_creation = "semantic_cache = SemanticCache(" in content
        has_chinese_embeddings = "ChineseEmbeddings" in content
        has_cache_strategy_param = "CacheStrategy(semantic_cache=semantic_cache)" in content

        all_checks = [
            ("Import SemanticCache", has_import),
            ("Create semantic_cache", has_creation),
            ("Use ChineseEmbeddings", has_chinese_embeddings),
            ("Pass to CacheStrategy", has_cache_strategy_param),
        ]

        passed = sum(1 for _, check in all_checks if check)

        print(f"\n[{filepath}]")
        for name, check in all_checks:
            status = "[OK]" if check else "[MISSING]"
            print(f"  {status} {name}")

        if passed == len(all_checks):
            print(f"  [PASS] All checks passed ({passed}/{len(all_checks)})")
        else:
            print(f"  [FAIL] Some checks missing ({passed}/{len(all_checks)})")

    print("\n" + "=" * 60)
    print("Verification complete")


if __name__ == "__main__":
    check_semantic_cache_integration()