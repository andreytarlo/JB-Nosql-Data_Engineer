"""
Phase 1 black-box functional tests.

All assertions go through the DBAccess interface only — no ORM imports,
no direct Postgres reads.
"""

import pytest

from ecommerce_pipeline.models.requests import OrderItemRequest
from ecommerce_pipeline.models.responses import (
    CategoryRevenueResponse,
    OrderResponse,
    OrderSnapshotResponse,
    ProductResponse,
)
from tests.conftest import insert_product_mongo, insert_snapshot_mongo


# ---------------------------------------------------------------------------
# MongoDB — get_product
# ---------------------------------------------------------------------------


def test_get_product_found(db_phase1, mongo_db):
    insert_product_mongo(
        mongo_db,
        id=1001,
        name="MacBook Pro 16",
        price=2499.99,
        stock_quantity=5,
        category="electronics",
        description="Apple laptop",
        category_fields={
            "cpu": "M3",
            "ram_gb": 16,
            "storage_gb": 512,
            "screen_inches": 16.0,
        },
    )
    product = db_phase1.get_product(1001)
    assert product is not None
    assert isinstance(product, ProductResponse)
    assert product.id == 1001
    assert product.name == "MacBook Pro 16"
    assert product.price == pytest.approx(2499.99)
    assert product.stock_quantity == 5
    assert product.category == "electronics"
    assert product.description == "Apple laptop"
    cf = product.category_fields
    assert set(cf.keys()) == {"cpu", "ram_gb", "storage_gb", "screen_inches"}
    assert cf["cpu"] == "M3"
    assert cf["ram_gb"] == 16


def test_get_product_clothing(db_phase1, mongo_db):
    insert_product_mongo(
        mongo_db,
        id=1002,
        name="Cotton T-Shirt",
        price=19.99,
        stock_quantity=100,
        category="clothing",
        description="Comfy shirt",
        category_fields={
            "material": "cotton",
            "sizes": ["S", "M", "L"],
            "colors": ["red", "blue"],
        },
    )
    product = db_phase1.get_product(1002)
    assert product is not None
    cf = product.category_fields
    assert isinstance(cf["sizes"], list)
    assert "M" in cf["sizes"]


def test_get_product_not_found(db_phase1, mongo_db):
    assert db_phase1.get_product(99999) is None


# ---------------------------------------------------------------------------
# MongoDB — search_products
# ---------------------------------------------------------------------------


def test_search_products_by_category(db_phase1, mongo_db):
    insert_product_mongo(mongo_db, id=2001, name="Phone", category="electronics")
    insert_product_mongo(mongo_db, id=2002, name="Tablet", category="electronics")
    insert_product_mongo(mongo_db, id=2003, name="Novel", category="books")

    results = db_phase1.search_products(category="electronics")
    assert len(results) == 2
    returned_ids = {p.id for p in results}
    assert returned_ids == {2001, 2002}


def test_search_products_by_name(db_phase1, mongo_db):
    insert_product_mongo(mongo_db, id=2004, name="Laptop Pro", category="electronics")
    insert_product_mongo(mongo_db, id=2005, name="Wireless Mouse", category="electronics")

    results = db_phase1.search_products(q="laptop")
    assert len(results) == 1
    assert results[0].name == "Laptop Pro"


def test_search_products_combined(db_phase1, mongo_db):
    insert_product_mongo(mongo_db, id=2006, name="Gaming Laptop", category="electronics")
    insert_product_mongo(mongo_db, id=2007, name="Laptop Bag", category="accessories")
    insert_product_mongo(mongo_db, id=2008, name="Keyboard", category="electronics")

    results = db_phase1.search_products(category="electronics", q="laptop")
    assert len(results) == 1
    assert results[0].id == 2006


def test_search_products_no_filter(db_phase1, mongo_db):
    insert_product_mongo(mongo_db, id=2009, name="Item A", category="electronics")
    insert_product_mongo(mongo_db, id=2010, name="Item B", category="books")
    insert_product_mongo(mongo_db, id=2011, name="Item C", category="clothing")

    results = db_phase1.search_products()
    assert len(results) == 3


# ---------------------------------------------------------------------------
# MongoDB — order snapshots
# ---------------------------------------------------------------------------


def test_save_order_snapshot(db_phase1, mongo_db):
    from ecommerce_pipeline.models.responses import OrderCustomerEmbed, OrderItemResponse

    result = db_phase1.save_order_snapshot(
        order_id=42,
        customer=OrderCustomerEmbed(id=1, name="Alice", email="a@b.com"),
        items=[
            OrderItemResponse(
                product_id=1,
                product_name="Laptop",
                quantity=2,
                unit_price=999.99,
            )
        ],
        total_amount=1999.98,
        status="completed",
        created_at="2025-01-15T10:30:00",
    )
    assert isinstance(result, str)

    snapshot = db_phase1.get_order(42)
    assert snapshot is not None
    assert isinstance(snapshot, OrderSnapshotResponse)
    assert snapshot.order_id == 42
    assert snapshot.customer.name == "Alice"
    assert snapshot.total_amount == pytest.approx(1999.98)
    assert snapshot.status == "completed"
    assert snapshot.created_at == "2025-01-15T10:30:00"
    assert len(snapshot.items) == 1
    assert snapshot.items[0].product_name == "Laptop"


def test_get_order_not_found(db_phase1, mongo_db):
    assert db_phase1.get_order(99999) is None


def test_get_order_history(db_phase1, mongo_db):
    customer = {"id": 5, "name": "Bob", "email": "bob@example.com"}
    insert_snapshot_mongo(
        mongo_db,
        order_id=100,
        customer=customer,
        items=[{"product_id": 1, "product_name": "A", "quantity": 1, "unit_price": 10.0}],
        total_amount=10.0,
        status="completed",
        created_at="2025-01-01T08:00:00",
    )
    insert_snapshot_mongo(
        mongo_db,
        order_id=101,
        customer=customer,
        items=[{"product_id": 2, "product_name": "B", "quantity": 1, "unit_price": 20.0}],
        total_amount=20.0,
        status="completed",
        created_at="2025-06-15T12:00:00",
    )

    history = db_phase1.get_order_history(customer_id=5)
    assert len(history) == 2
    assert isinstance(history[0], OrderSnapshotResponse)
    # Newest first
    assert history[0].order_id == 101
    assert history[1].order_id == 100


def test_get_order_history_empty(db_phase1, mongo_db):
    history = db_phase1.get_order_history(customer_id=99999)
    assert history == []


# ---------------------------------------------------------------------------
# Postgres — create_order (requires seeded data)
# ---------------------------------------------------------------------------


def test_create_order_success(db_phase1, seeded):
    result = db_phase1.create_order(
        customer_id=1, items=[OrderItemRequest(product_id=1, quantity=2)]
    )

    assert isinstance(result, OrderResponse)
    assert isinstance(result.order_id, int)
    assert result.customer_id == 1
    assert result.status == "completed"
    assert isinstance(result.total_amount, (int, float))
    assert result.total_amount > 0
    assert isinstance(result.created_at, str)
    assert isinstance(result.items, list)
    assert len(result.items) == 1
    item = result.items[0]
    assert item.product_id == 1
    assert item.product_name is not None
    assert item.quantity == 2
    assert isinstance(item.unit_price, (int, float))


def test_create_order_reduces_stock(db_phase1, seeded):
    """Verify stock is decremented by placing orders until stock runs out.

    Product 1 has stock_quantity=25. If we order 25 units successfully,
    then ordering 1 more must fail with insufficient stock.
    """
    # Order all available stock
    db_phase1.create_order(
        customer_id=1, items=[OrderItemRequest(product_id=1, quantity=25)]
    )

    # Next order for even 1 unit should fail — stock is exhausted
    with pytest.raises(ValueError, match="Insufficient stock"):
        db_phase1.create_order(
            customer_id=1, items=[OrderItemRequest(product_id=1, quantity=1)]
        )


def test_create_order_insufficient_stock(db_phase1, seeded):
    with pytest.raises(ValueError, match="Insufficient stock"):
        db_phase1.create_order(
            customer_id=1,
            items=[OrderItemRequest(product_id=1, quantity=999999)],
        )


def test_create_order_atomic_rollback(db_phase1, seeded, mongo_db):
    before = db_phase1.get_product(1)
    assert before is not None
    stock_before = before.stock_quantity

    with pytest.raises(ValueError):
        db_phase1.create_order(
            customer_id=1,
            items=[
                OrderItemRequest(product_id=1, quantity=2),
                OrderItemRequest(product_id=2, quantity=999999),
            ],
        )

    after = db_phase1.get_product(1)
    assert after is not None
    assert after.stock_quantity == stock_before


def test_create_order_creates_snapshot(db_phase1, seeded):
    result = db_phase1.create_order(
        customer_id=1, items=[OrderItemRequest(product_id=1, quantity=1)]
    )
    order_id = result.order_id

    snapshot = db_phase1.get_order(order_id)
    assert snapshot is not None
    assert snapshot.total_amount == pytest.approx(result.total_amount)


# ---------------------------------------------------------------------------
# Postgres — revenue_by_category (requires seeded data)
# ---------------------------------------------------------------------------


def test_revenue_by_category(db_phase1, seeded):
    # Product 1 is electronics (price 1299.99), product IDs in seed cover
    # multiple categories.  Create orders in two different categories.
    db_phase1.create_order(
        customer_id=1, items=[OrderItemRequest(product_id=1, quantity=1)]
    )
    db_phase1.create_order(
        customer_id=2, items=[OrderItemRequest(product_id=2, quantity=1)]
    )

    result = db_phase1.revenue_by_category()
    assert isinstance(result, list)
    assert len(result) >= 1
    for entry in result:
        assert isinstance(entry, CategoryRevenueResponse)
        assert isinstance(entry.category, str)
        assert isinstance(entry.total_revenue, (int, float))

    # Verify descending sort
    revenues = [e.total_revenue for e in result]
    assert revenues == sorted(revenues, reverse=True)


def test_revenue_by_category_empty(db_phase1, seeded):
    result = db_phase1.revenue_by_category()
    assert result == []
