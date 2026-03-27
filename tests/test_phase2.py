"""
Phase 2 — Redis integration tests.

Tests cover:
  - Read-through cache (product:{id})
  - Cache invalidation
  - TTL enforcement
  - Recently-viewed list (recently_viewed:{customer_id})
  - Inventory counters (inventory:{id})
"""

import pytest

from ecommerce_pipeline.models.requests import OrderItemRequest
from ecommerce_pipeline.models.responses import ProductResponse
from tests.conftest import insert_product_mongo


# ---------------------------------------------------------------------------
# Cache tests (independent of seed — use insert_product_mongo)
# ---------------------------------------------------------------------------


def test_cache_populated_on_first_read(db_phase2, mongo_db, redis_client):
    """get_product should populate the Redis cache on first read."""
    insert_product_mongo(mongo_db, id=1, name="Widget", price=9.99, stock_quantity=5)

    db_phase2.get_product(1)

    assert redis_client.get("product:1") is not None


def test_cache_serves_stale_data(db_phase2, mongo_db, redis_client):
    """After caching, get_product should return stale data until invalidated."""
    insert_product_mongo(mongo_db, id=1, name="Original Name", price=9.99, stock_quantity=5)

    # Populate cache
    db_phase2.get_product(1)

    # Update MongoDB directly (bypass cache)
    mongo_db["product_catalog"].update_one({"id": 1}, {"$set": {"name": "Updated Name"}})

    # Should still return the cached (old) name
    product = db_phase2.get_product(1)
    assert product.name == "Original Name"


def test_invalidate_clears_cache(db_phase2, mongo_db, redis_client):
    """After invalidation, get_product should fetch fresh data from MongoDB."""
    insert_product_mongo(mongo_db, id=1, name="Original Name", price=9.99, stock_quantity=5)

    # Populate cache
    db_phase2.get_product(1)

    # Invalidate
    db_phase2.invalidate_product_cache(1)

    # Update MongoDB
    mongo_db["product_catalog"].update_one({"id": 1}, {"$set": {"name": "Updated Name"}})

    # Should now return the updated name
    product = db_phase2.get_product(1)
    assert product.name == "Updated Name"


def test_cache_ttl(db_phase2, mongo_db, redis_client):
    """Cached product keys should have a TTL between 1 and 300 seconds."""
    insert_product_mongo(mongo_db, id=1, name="Widget", price=9.99, stock_quantity=5)

    db_phase2.get_product(1)

    ttl = redis_client.ttl("product:1")
    assert ttl > 0
    assert ttl <= 300


def test_cache_miss_no_write(db_phase2, mongo_db, redis_client):
    """A cache miss for a non-existent product should NOT write to Redis."""
    db_phase2.get_product(99999)

    assert redis_client.get("product:99999") is None


# ---------------------------------------------------------------------------
# Recently-viewed tests (independent of seed)
# ---------------------------------------------------------------------------


def test_record_and_get_recently_viewed(db_phase2, redis_client):
    """Recently viewed should return product ids most-recent-first."""
    db_phase2.record_product_view(customer_id=1, product_id=5)
    db_phase2.record_product_view(customer_id=1, product_id=3)
    db_phase2.record_product_view(customer_id=1, product_id=1)

    result = db_phase2.get_recently_viewed(customer_id=1)
    assert result == [1, 3, 5]


def test_recently_viewed_bounded_at_10(db_phase2, redis_client):
    """Recently viewed list should keep at most 10 entries."""
    for pid in range(1, 13):
        db_phase2.record_product_view(customer_id=1, product_id=pid)

    result = db_phase2.get_recently_viewed(customer_id=1)
    assert len(result) == 10
    assert result == [12, 11, 10, 9, 8, 7, 6, 5, 4, 3]


def test_recently_viewed_empty(db_phase2, redis_client):
    """A customer with no views should get an empty list."""
    result = db_phase2.get_recently_viewed(customer_id=999)
    assert result == []


def test_recently_viewed_returns_ints(db_phase2, redis_client):
    """Recently viewed product ids must be ints, not strings."""
    db_phase2.record_product_view(customer_id=1, product_id=42)

    result = db_phase2.get_recently_viewed(customer_id=1)
    assert len(result) > 0
    for item in result:
        assert isinstance(item, int), f"Expected int, got {type(item)}: {item!r}"


# ---------------------------------------------------------------------------
# Inventory counter tests (require seeded fixture)
# ---------------------------------------------------------------------------


def test_inventory_counters_seeded(db_phase2, redis_client, seeded):
    """After seed, inventory:1 should match product 1's stock_quantity (25)."""
    value = redis_client.get("inventory:1")
    assert value is not None
    assert int(value) == 25


def test_create_order_decrements_counter(db_phase2, redis_client, seeded):
    """create_order should decrement the Redis inventory counter."""
    initial = int(redis_client.get("inventory:1"))

    db_phase2.create_order(
        customer_id=1, items=[OrderItemRequest(product_id=1, quantity=2)]
    )

    after = int(redis_client.get("inventory:1"))
    assert after == initial - 2


def test_failed_order_no_counter_change(db_phase2, redis_client, seeded):
    """A failed order (insufficient stock) should not change the counter."""
    initial = int(redis_client.get("inventory:1"))

    with pytest.raises(ValueError):
        db_phase2.create_order(
            customer_id=1, items=[OrderItemRequest(product_id=1, quantity=999999)]
        )

    after = int(redis_client.get("inventory:1"))
    assert after == initial
