"""查看记忆系统中的实际数据内容"""

import asyncio
import redis
import json
from datetime import datetime

async def view_chroma_data():
    """查看ChromaDB中的语义记忆"""
    print("=" * 60)
    print("ChromaDB 语义记忆数据")
    print("=" * 60)

    try:
        import chromadb

        # 尝试连接到不同的ChromaDB实例
        clients_to_try = [
            ("HTTP Client (port 8001)", lambda: chromadb.HttpClient(host=localhost, port=8001)),
            ("HTTP Client (port 8000)", lambda: chromadb.HttpClient(host=localhost, port=8000)),
            ("Embedded Client", lambda: chromadb.Client())
        ]

        client = None

        for name, create_func in clients_to_try:
            try:
                client = create_func()
                collections = client.list_collections()
                print(f"OK: Using {name}")
                break
            except:
                continue

        if not client:
            print("ERROR: Cannot connect to ChromaDB")
            return

        # 获取所有collections
        collections = client.list_collections()

        if not collections:
            print("No data in ChromaDB")
        else:
            print(f"Found {len(collections)} collection(s):")
            
            for collection in collections:
                print(f"
Collection: {collection.name}")
                
                try:
                    count = collection.count()
                    print(f"Record count: {count}")

                    if count > 0:
                        results = collection.get()
                        print(f"Data content:")

                        for i, (doc_id, document, metadata) in enumerate(zip(
                            results["ids"][0][:5],
                            results["documents"][0][:5],
                            results["metadatas"][0][:5]
                        )):
                            print(f"  [{i+1}] {document[:60]}...")
                except Exception as e:
                    print(f"ERROR: {e}")

        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False

async def view_redis_data():
    """查看Redis中的情景记忆"""
    print("
" + "=" * 60)
    print("Redis 情景记忆数据")
    print("=" * 60)

    try:
        r = redis.Redis(host=localhost, port=6379, db=0, decode_responses=True)
        r.ping()
        print("OK: Redis connected")
        print(f"Redis version: {r.info()["redis_version"]}
")

        # 显示所有键
        all_keys = r.keys("*")
        
        if not all_keys:
            print("Redis is empty")
        else:
            print(f"Total keys: {len(all_keys)}
")
            
            # 显示前10个键
            print("First 10 keys:")
            for i, key in enumerate(all_keys[:10], 1):
                key_type = r.type(key)
                print(f"  [{i}] {key} ({key_type})")
                
                # 显示内容预览
                if key_type == "string":
                    value = r.get(key)
                    print(f"      Value: {value[:50]}...")
                elif key_type == "list":
                    count = r.llen(key)
                    print(f"      List items: {count}")

        # 检查内存使用
        info = r.info("memory")
        print(f"
Redis memory usage: {info["used_memory_human"]}")

        return True
    except Exception as e:
        print(f"ERROR: {e}")
        return False

async def main():
    print("
" + "=" * 60)
    print("Memory System Data Viewer")
    print("=" * 60)
    
    await view_chroma_data()
    await view_redis_data()

if __name__ == "__main__":
    asyncio.run(main())
