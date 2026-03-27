"""
DBAccess — the data access layer.

This is one of the files you implement. The web API is already wired up;
every route calls one method on this class. Your job is to replace each
`raise NotImplementedError(...)` with a real implementation.

Work through the phases in order. Read the corresponding lesson file before
starting each phase.

You also implement scripts/migrate.py and scripts/seed.py alongside this file.
"""

from __future__ import annotations

import json
import logging
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import neo4j
    import redis as redis_lib
    from pymongo.database import Database as MongoDatabase
    from sqlalchemy.orm import sessionmaker

    from ecommerce_pipeline.models.requests import OrderItemRequest
    from ecommerce_pipeline.models.responses import (
        CategoryRevenueResponse,
        OrderCustomerEmbed,
        OrderItemResponse,
        OrderResponse,
        OrderSnapshotResponse,
        ProductResponse,
        RecommendationResponse,
    )

logger = logging.getLogger(__name__)


class DBAccess:
    def __init__(
        self,
        pg_session_factory: sessionmaker,
        mongo_db: MongoDatabase,
        redis_client: redis_lib.Redis | None = None,
        neo4j_driver: neo4j.Driver | None = None,
    ) -> None:
        self._pg_session_factory = pg_session_factory
        self._mongo_db = mongo_db
        self._redis = redis_client
        self._neo4j = neo4j_driver

    # ── Phase 1 ───────────────────────────────────────────────────────────────

    def create_order(self, customer_id: int, items: list[OrderItemRequest]) -> OrderResponse:
        """Place an order atomically.

        See OrderItemRequest in models/requests.py for the input shape.
        See OrderResponse in models/responses.py for the return shape.

        Raises ValueError if any product has insufficient stock. When that
        happens, no data is modified in any database.

        After the order is persisted transactionally, a denormalized snapshot
        is saved for read access, and downstream counters and graph edges are
        updated (best-effort, does not roll back the order on failure).
        """
        from ecommerce_pipeline.postgres_models import Customer, Order, OrderItem, Product
        from ecommerce_pipeline.models.responses import (
            OrderCustomerEmbed,
            OrderItemResponse,
            OrderResponse,
        )

        session = self._pg_session_factory()
        try:
            # Validate stock for all items before making any changes
            products_with_qty = []
            for item_req in items:
                product = session.get(Product, item_req.product_id)
                if product is None:
                    raise ValueError(f"Product {item_req.product_id} not found")
                if product.stock_quantity < item_req.quantity:
                    raise ValueError(
                        f"Insufficient stock for product {item_req.product_id}: "
                        f"requested {item_req.quantity}, available {product.stock_quantity}"
                    )
                products_with_qty.append((product, item_req.quantity))

            total_amount = sum(float(p.price) * qty for p, qty in products_with_qty)

            order = Order(customer_id=customer_id, total_amount=total_amount, status="completed")
            session.add(order)
            session.flush()  # populate order.id

            item_responses = []
            for product, quantity in products_with_qty:
                product.stock_quantity -= quantity
                session.add(OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=float(product.price),
                ))
                item_responses.append(OrderItemResponse(
                    product_id=product.id,
                    product_name=product.name,
                    quantity=quantity,
                    unit_price=float(product.price),
                ))

            customer_obj = session.get(Customer, customer_id)
            customer_embed = OrderCustomerEmbed(
                id=customer_obj.id,
                name=customer_obj.name,
                email=customer_obj.email,
            )

            # Collect ids before session closes (ORM objects detach on close)
            items_for_redis = [(p.id, qty) for p, qty in products_with_qty]

            session.commit()
            session.refresh(order)

            order_id = order.id
            created_at_str = order.created_at.isoformat()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        # Decrement Redis inventory counters (best-effort, after PG commit)
        if self._redis:
            for product_id, quantity in items_for_redis:
                self._redis.decrby(f"inventory:{product_id}", quantity)

        # Save MongoDB snapshot (best-effort, outside transaction)
        self.save_order_snapshot(
            order_id=order_id,
            customer=customer_embed,
            items=item_responses,
            total_amount=total_amount,
            status="completed",
            created_at=created_at_str,
        )

        return OrderResponse(
            order_id=order_id,
            customer_id=customer_id,
            status="completed",
            total_amount=total_amount,
            created_at=created_at_str,
            items=item_responses,
        )

    def get_product(self, product_id: int) -> ProductResponse | None:
        """Fetch a product by its integer ID.

        See ProductResponse in models/responses.py for the return shape.
        Returns None if not found.
        """
        from ecommerce_pipeline.models.responses import ProductResponse

        cache_key = f"product:{product_id}"

        # Cache-aside: check Redis first
        if self._redis:
            cached = self._redis.get(cache_key)
            if cached:
                return ProductResponse.model_validate_json(cached)

        doc = self._mongo_db["product_catalog"].find_one({"id": product_id})
        if doc is None:
            return None

        product = ProductResponse(
            id=doc["id"],
            name=doc["name"],
            price=doc["price"],
            stock_quantity=doc["stock_quantity"],
            category=doc["category"],
            description=doc["description"],
            category_fields=doc.get("category_fields", {}),
        )

        # Populate cache with 300-second TTL
        if self._redis:
            self._redis.set(cache_key, product.model_dump_json(), ex=300)

        return product

    def search_products(
        self,
        category: str | None = None,
        q: str | None = None,
    ) -> list[ProductResponse]:
        """Search the product catalog with optional filters.

        category: exact match on the category field
        q: case-insensitive substring match on the product name
        Both filters are ANDed together. Returns all products if both are None.
        """
        from ecommerce_pipeline.models.responses import ProductResponse

        query: dict = {}
        if category is not None:
            query["category"] = category
        if q is not None:
            query["name"] = {"$regex": q, "$options": "i"}

        docs = self._mongo_db["product_catalog"].find(query)
        return [
            ProductResponse(
                id=doc["id"],
                name=doc["name"],
                price=doc["price"],
                stock_quantity=doc["stock_quantity"],
                category=doc["category"],
                description=doc["description"],
                category_fields=doc.get("category_fields", {}),
            )
            for doc in docs
        ]

    def save_order_snapshot(
        self,
        order_id: int,
        customer: OrderCustomerEmbed,
        items: list[OrderItemResponse],
        total_amount: float,
        status: str,
        created_at: str,
    ) -> str:
        """Save a denormalized order snapshot for fast read access.

        See OrderCustomerEmbed and OrderItemResponse in models/responses.py
        for the input shapes.

        Embeds all customer and product details as they existed at the time
        of the order, so the snapshot remains accurate even if prices or
        names change later.

        Returns a string identifier for the saved document.

        Called internally by create_order after the transactional write
        commits. Not called directly by routes.
        """
        doc = {
            "order_id": order_id,
            "customer": customer.model_dump(),
            "items": [item.model_dump() for item in items],
            "total_amount": total_amount,
            "status": status,
            "created_at": created_at,
        }
        result = self._mongo_db["order_snapshots"].insert_one(doc)
        return str(result.inserted_id)

    def get_order(self, order_id: int) -> OrderSnapshotResponse | None:
        """Fetch a single order snapshot by order_id.

        See OrderSnapshotResponse in models/responses.py for the return shape.
        Returns None if not found.
        """
        from ecommerce_pipeline.models.responses import OrderSnapshotResponse

        doc = self._mongo_db["order_snapshots"].find_one({"order_id": order_id})
        if doc is None:
            return None
        return OrderSnapshotResponse(**{k: v for k, v in doc.items() if k != "_id"})

    def get_order_history(self, customer_id: int) -> list[OrderSnapshotResponse]:
        """Fetch all order snapshots for a customer, sorted by created_at descending.

        Returns an empty list if the customer has no orders.
        """
        from ecommerce_pipeline.models.responses import OrderSnapshotResponse

        docs = self._mongo_db["order_snapshots"].find(
            {"customer.id": customer_id},
            sort=[("created_at", -1)],
        )
        return [
            OrderSnapshotResponse(**{k: v for k, v in doc.items() if k != "_id"})
            for doc in docs
        ]

    def revenue_by_category(self) -> list[CategoryRevenueResponse]:
        """Compute total revenue per product category, sorted by total_revenue descending.

        See CategoryRevenueResponse in models/responses.py for the return shape.
        """
        from sqlalchemy import func, select
        from ecommerce_pipeline.postgres_models import OrderItem, Product
        from ecommerce_pipeline.models.responses import CategoryRevenueResponse

        session = self._pg_session_factory()
        try:
            stmt = (
                select(
                    Product.category,
                    func.sum(OrderItem.unit_price * OrderItem.quantity).label("total_revenue"),
                )
                .join(Product, OrderItem.product_id == Product.id)
                .group_by(Product.category)
                .order_by(func.sum(OrderItem.unit_price * OrderItem.quantity).desc())
            )
            rows = session.execute(stmt).all()
            return [
                CategoryRevenueResponse(category=row.category, total_revenue=float(row.total_revenue))
                for row in rows
            ]
        finally:
            session.close()

    # ── Phase 2 ───────────────────────────────────────────────────────────────
    #
    # In this phase you also need to:
    #   - Update create_order to DECR Redis inventory counters after the
    #     Postgres transaction succeeds.
    #   - Optionally, add a fast pre-check: before starting the Postgres
    #     transaction, check the Redis counter. If it shows insufficient
    #     stock, fail fast without hitting Postgres.
    #   - Update scripts/seed.py to initialize inventory counters in Redis.
    #   - Add cache-aside logic to get_product (check Redis first, populate
    #     on miss with a 300-second TTL).

    def invalidate_product_cache(self, product_id: int) -> None:
        """Remove a product's cached entry.

        Call this after updating a product's data so the next read fetches
        fresh data from the primary store. No-op if no entry exists.
        """
        if self._redis:
            self._redis.delete(f"product:{product_id}")

    def record_product_view(self, customer_id: int, product_id: int) -> None:
        """Record that a customer viewed a product.

        Maintains a bounded, ordered list of the customer's most recently
        viewed products (most recent first, capped at 10 entries).
        """
        if self._redis:
            key = f"recently_viewed:{customer_id}"
            self._redis.lpush(key, product_id)
            self._redis.ltrim(key, 0, 9)

    def get_recently_viewed(self, customer_id: int) -> list[int]:
        """Return up to 10 recently viewed product IDs for a customer.

        Returns IDs as integers, most recently viewed first.
        Returns an empty list if no views have been recorded.
        """
        if not self._redis:
            return []
        items = self._redis.lrange(f"recently_viewed:{customer_id}", 0, 9)
        return [int(x) for x in items]

    # ── Phase 3 ───────────────────────────────────────────────────────────────
    #
    # In this phase you also need to:
    #   - Update create_order to MERGE co-purchase edges in Neo4j for every
    #     pair of products in the order, incrementing the edge weight.
    #   - Update scripts/migrate.py to create Neo4j constraints.
    #   - Update scripts/seed.py to build the co-purchase graph from
    #     seed_data/historical_orders.json.

    def get_recommendations(self, product_id: int, limit: int = 5) -> list[RecommendationResponse]:
        """Return product recommendations based on co-purchase patterns.

        See RecommendationResponse in models/responses.py for the return shape.
        Sorted by score descending. Returns an empty list if no co-purchase relationships exist.
        """
        raise NotImplementedError("Phase 3: implement get_recommendations")
