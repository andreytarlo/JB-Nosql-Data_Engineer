"""
Shared fixtures for all test phases.

Database isolation strategy:
  - Postgres:  separate test database (ecommerce_test), auto-created if missing.
               Tables created once per session (via student's migrate), data
               truncated between tests.
  - MongoDB:   separate test database (ecommerce_test). Data cleared between tests.
  - Redis:     db=1 (separate from app db=0). Flushed between tests.
  - Neo4j:     all nodes/relationships deleted between tests.

Connection defaults match docker-compose.yml. Override with env vars if needed.
"""

import os

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

from ecommerce_pipeline.db_access import DBAccess


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _pg_admin_url() -> str:
    """URL for the default 'postgres' database (used to create test DB)."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "postgres")
    pwd = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/postgres"


def _pg_test_url() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_USER", "postgres")
    pwd = os.environ.get("POSTGRES_PASSWORD", "postgres")
    db = os.environ.get("POSTGRES_TEST_DB", "ecommerce_test")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


def _mongo_test_db_name() -> str:
    return os.environ.get("MONGO_TEST_DB", "ecommerce_test")


def _mongo_host() -> str:
    return os.environ.get("MONGO_HOST", "localhost")


def _mongo_port() -> int:
    return int(os.environ.get("MONGO_PORT", "27017"))


def _redis_host() -> str:
    return os.environ.get("REDIS_HOST", "localhost")


def _redis_port() -> int:
    return int(os.environ.get("REDIS_PORT", "6379"))


def _neo4j_uri() -> str:
    host = os.environ.get("NEO4J_HOST", "localhost")
    port = os.environ.get("NEO4J_BOLT_PORT", "7687")
    return f"bolt://{host}:{port}"


def _neo4j_auth() -> tuple[str, str]:
    user = os.environ.get("NEO4J_USER", "neo4j")
    pwd = os.environ.get("NEO4J_PASSWORD", "neo4jpassword")
    return user, pwd


# ---------------------------------------------------------------------------
# Auto-create test database
# ---------------------------------------------------------------------------

def _ensure_test_db_exists():
    """Create the ecommerce_test Postgres database if it doesn't exist."""
    db_name = os.environ.get("POSTGRES_TEST_DB", "ecommerce_test")
    admin_engine = create_engine(_pg_admin_url(), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        )
        if not result.scalar():
            conn.execute(text(f"CREATE DATABASE {db_name}"))
    admin_engine.dispose()


# ---------------------------------------------------------------------------
# Session-scoped fixtures — set up once for the entire test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_engine():
    """Create test engine. Auto-creates the test DB, resets, and runs migrate."""
    _ensure_test_db_exists()

    engine = create_engine(_pg_test_url(), echo=False)

    # Import student models to register with Base.metadata
    import ecommerce_pipeline.postgres_models  # noqa: F401
    from ecommerce_pipeline.postgres_models import Base
    from ecommerce_pipeline.reset import reset_all

    # Create a temporary mongo connection for reset
    client = MongoClient(_mongo_host(), _mongo_port())
    mongo_db = client[_mongo_test_db_name()]

    # Reset and run student's migration
    reset_all(engine, mongo_db)
    from scripts.migrate import migrate
    migrate(engine, mongo_db)

    client.close()

    yield engine

    Base.metadata.drop_all(engine)
    engine.dispose()


# ---------------------------------------------------------------------------
# Function-scoped fixtures — reset state between tests
# ---------------------------------------------------------------------------

@pytest.fixture
def pg_session_factory(pg_engine):
    """Return a sessionmaker bound to the test engine."""
    return sessionmaker(bind=pg_engine)


@pytest.fixture
def mongo_db():
    """Return pymongo Database for the test database."""
    client = MongoClient(_mongo_host(), _mongo_port())
    db = client[_mongo_test_db_name()]
    yield db
    client.close()


@pytest.fixture
def redis_client():
    """Return redis.Redis on db=1 (separate from app db=0)."""
    import redis as redis_lib

    r = redis_lib.Redis(
        host=_redis_host(), port=_redis_port(), db=1, decode_responses=True
    )
    yield r
    r.close()


@pytest.fixture
def neo4j_driver():
    """Return neo4j.Driver."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(_neo4j_uri(), auth=_neo4j_auth())
    yield driver
    driver.close()


@pytest.fixture(autouse=True)
def _clean_between_tests(pg_engine, mongo_db, redis_client, neo4j_driver):
    """Clear all data before each test, preserving structure."""
    from ecommerce_pipeline.reset import clear_data

    clear_data(pg_engine, mongo_db, redis_client, neo4j_driver)
    yield


@pytest.fixture
def seeded(pg_engine, mongo_db, redis_client, neo4j_driver):
    """Run student's seed function. Use for tests that need baseline data.

    Tests that only need MongoDB data can insert via raw pymongo instead.
    Tests that need Postgres data (create_order, revenue_by_category) should
    use this fixture.
    """
    from scripts.seed import seed

    seed(pg_engine, mongo_db, redis_client, neo4j_driver)


# ---------------------------------------------------------------------------
# DBAccess fixtures for each phase
# ---------------------------------------------------------------------------

@pytest.fixture
def db_phase1(pg_session_factory, mongo_db):
    """Phase 1: Postgres + MongoDB only."""
    return DBAccess(pg_session_factory, mongo_db)


@pytest.fixture
def db_phase2(pg_session_factory, mongo_db, redis_client):
    """Phase 2: Postgres + MongoDB + Redis."""
    return DBAccess(pg_session_factory, mongo_db, redis_client=redis_client)


@pytest.fixture
def db(pg_session_factory, mongo_db, redis_client, neo4j_driver):
    """Phase 3 / full: all four databases."""
    return DBAccess(
        pg_session_factory, mongo_db,
        redis_client=redis_client, neo4j_driver=neo4j_driver,
    )


# ---------------------------------------------------------------------------
# Raw MongoDB insert helpers (schemaless — match return contract shapes)
# ---------------------------------------------------------------------------

def insert_product_mongo(mongo_db, *, id, name="Test Product", price=99.99,
                          stock_quantity=10, category="electronics",
                          description="A test product.",
                          category_fields=None):
    """Insert a product document into MongoDB product_catalog."""
    doc = {
        "id": id,
        "name": name,
        "price": price,
        "stock_quantity": stock_quantity,
        "category": category,
        "description": description,
        "category_fields": category_fields or {},
    }
    mongo_db["product_catalog"].insert_one(dict(doc))
    return doc


def insert_snapshot_mongo(mongo_db, *, order_id, customer, items,
                           total_amount, status="completed",
                           created_at="2025-01-01T10:00:00"):
    """Insert an order snapshot document into MongoDB order_snapshots."""
    doc = {
        "order_id": order_id,
        "customer": customer,
        "items": items,
        "total_amount": total_amount,
        "status": status,
        "created_at": created_at,
    }
    mongo_db["order_snapshots"].insert_one(dict(doc))
    return doc
