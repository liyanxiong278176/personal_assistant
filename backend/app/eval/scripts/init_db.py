"""初始化评估数据库脚本

Usage:
    python -m app.eval.scripts.init_db
"""
import asyncio
import logging
from pathlib import Path

from app.eval.storage import EvalStorage

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """初始化数据库"""
    # 确保数据目录存在
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)

    db_path = data_dir / "eval.db"

    logger.info(f"Initializing evaluation database at: {db_path}")

    storage = EvalStorage(str(db_path))
    await storage.init_db()

    logger.info("✓ Database initialized successfully")


if __name__ == "__main__":
    asyncio.run(main())
