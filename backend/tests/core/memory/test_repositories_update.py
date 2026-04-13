import pytest
from app.db.semantic_repo import ChromaDBSemanticRepository
from app.db.vector_store import VectorStore

@pytest.mark.asyncio
async def test_update_metadata():
    store = VectorStore()
    repo = ChromaDBSemanticRepository(store)

    # Add a memory and capture the returned ID
    item_id = await repo.add("测试内容", [0.1]*384, {"user_id": "test", "temp": "old"})
    assert item_id, "add() should return a non-empty ID"

    # Update metadata using the real ID from add()
    success = await repo.update_metadata(
        item_id,
        {"temp": "new", "added": True}
    )

    assert success is True

    # Verify the update persisted (optional verification)
    # We can check by searching and finding the updated item
    results = await repo.search_similar([0.1]*384, "test", n_results=1)
    if results:
        updated_meta = results[0].get("metadata", {})
        assert updated_meta.get("temp") == "new"
        assert updated_meta.get("added") is True
