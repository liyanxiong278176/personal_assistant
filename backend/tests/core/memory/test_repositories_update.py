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

    # Verify the update persisted by searching with a large n_results
    # and filtering by our known item_id (avoids embedding model dependency)
    results = await repo.search_similar([0.1]*384, "test", n_results=50)
    # Find our specific item by id
    our_item = next((r for r in results if r.get("id") == item_id), None)
    assert our_item is not None, f"Updated item {item_id} not found in results"
    updated_meta = our_item.get("metadata", {})
    assert updated_meta.get("temp") == "new", f"Expected 'new', got {updated_meta.get('temp')}"
    assert updated_meta.get("added") is True
