"""
Phase 3 — Black-box functional tests for Neo4j recommendations.

Tests verify the co-purchase recommendation engine built from historical_orders.json:
  - get_recommendations returns correctly shaped, sorted, filtered results
  - create_order updates the Neo4j graph with new co-purchase edges

All tests use the full `db` fixture (Postgres + MongoDB + Redis + Neo4j).
Tests that need baseline data use the `seeded` fixture.
"""

import pytest  # noqa: F401

from ecommerce_pipeline.models.requests import OrderItemRequest
from ecommerce_pipeline.models.responses import RecommendationResponse


# ---------------------------------------------------------------------------
# Recommendation tests (seeded data from historical_orders.json)
# ---------------------------------------------------------------------------

def test_get_recommendations_shape(db, seeded):
    """get_recommendations returns a list of RecommendationResponse with product_id, name, and score."""
    result = db.get_recommendations(1)

    assert isinstance(result, list)
    assert len(result) > 0
    for item in result:
        assert isinstance(item, RecommendationResponse)
        assert isinstance(item.product_id, int)
        assert isinstance(item.name, str)
        assert isinstance(item.score, int)


def test_get_recommendations_sorted(db, seeded):
    """Recommendations are returned in descending order of score."""
    result = db.get_recommendations(1)

    assert len(result) >= 2
    scores = [item.score for item in result]
    assert scores == sorted(scores, reverse=True)


def test_get_recommendations_excludes_self(db, seeded):
    """The queried product must not appear in its own recommendations."""
    result = db.get_recommendations(1)

    product_ids = [item.product_id for item in result]
    assert 1 not in product_ids


def test_get_recommendations_respects_limit(db, seeded):
    """get_recommendations with limit=2 returns at most 2 results."""
    result = db.get_recommendations(product_id=1, limit=2)

    assert len(result) <= 2


def test_get_recommendations_empty(db, seeded):
    """get_recommendations returns [] for a product not in the graph."""
    result = db.get_recommendations(99999)

    assert result == []


def test_create_order_updates_graph(db, seeded):
    """create_order adds BOUGHT_TOGETHER edges for co-purchased products.

    Uses seeded data so Postgres customers/products and MongoDB catalog exist.
    After creating an order with products [1, 2], verifies the graph reflects
    the new co-purchase relationship.
    """
    db.create_order(customer_id=1, items=[
        OrderItemRequest(product_id=1, quantity=1),
        OrderItemRequest(product_id=2, quantity=1),
    ])

    # Product 2 should now appear in recommendations for product 1
    recs_for_1 = db.get_recommendations(1)
    rec_ids_for_1 = [r.product_id for r in recs_for_1]
    assert 2 in rec_ids_for_1

    # And product 1 should appear in recommendations for product 2
    recs_for_2 = db.get_recommendations(2)
    rec_ids_for_2 = [r.product_id for r in recs_for_2]
    assert 1 in rec_ids_for_2
