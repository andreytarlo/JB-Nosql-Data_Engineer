"""
Database connection management.

This module creates and exposes connection objects for all four databases.
The application imports `get_db_access` as a FastAPI dependency — you do not
need to change anything here.

Connections are created once at startup (module-level singletons).
Phase 2 and Phase 3 connections are created only when the matching environment
variables are present, so the app runs in Phase 1 without Redis or Neo4j.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pymongo

from ecommerce_pipeline.db_access import DBAccess

load_dotenv()


# ── PostgreSQL ────────────────────────────────────────────────────────────────

pg_host = os.environ.get("POSTGRES_HOST", "localhost")
pg_port = os.environ.get("POSTGRES_PORT", "5432")
pg_db = os.environ.get("POSTGRES_DB", "ecommerce")
pg_user = os.environ.get("POSTGRES_USER", "postgres")
pg_password = os.environ.get("POSTGRES_PASSWORD", "postgres")

pg_url = f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

_pg_engine = create_engine(pg_url)
_pg_session_factory = sessionmaker(bind=_pg_engine)


# ── MongoDB ───────────────────────────────────────────────────────────────────

mongo_host = os.environ.get("MONGO_HOST", "localhost")
mongo_port = int(os.environ.get("MONGO_PORT", "27017"))
mongo_db_name = os.environ.get("MONGO_DB", "ecommerce")

_mongo_client = pymongo.MongoClient(mongo_host, mongo_port)
_mongo_db = _mongo_client[mongo_db_name]


# ── Redis (Phase 2) ───────────────────────────────────────────────────────────

_redis_client = None

redis_host = os.environ.get("REDIS_HOST")
redis_port = int(os.environ.get("REDIS_PORT", "6379"))

if redis_host:
    import redis as redis_lib
    _redis_client = redis_lib.Redis(host=redis_host, port=redis_port, decode_responses=True)


# ── Neo4j (Phase 3) ───────────────────────────────────────────────────────────

_neo4j_driver = None

neo4j_host = os.environ.get("NEO4J_HOST")
neo4j_bolt_port = os.environ.get("NEO4J_BOLT_PORT", "7687")
neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
neo4j_password = os.environ.get("NEO4J_PASSWORD")

if neo4j_host and neo4j_password:
    import neo4j as neo4j_lib
    _neo4j_driver = neo4j_lib.GraphDatabase.driver(
        f"bolt://{neo4j_host}:{neo4j_bolt_port}",
        auth=(neo4j_user, neo4j_password),
    )


# ── Dependency ────────────────────────────────────────────────────────────────

def get_db_access() -> DBAccess:
    """FastAPI dependency that provides a configured DBAccess instance.

    Usage in a route:
        from fastapi import Depends
        from ecommerce_pipeline.db import get_db_access
        from ecommerce_pipeline.db_access import DBAccess

        @router.get("/example")
        def example(db: DBAccess = Depends(get_db_access)):
            return db.some_method()
    """
    return DBAccess(
        pg_session_factory=_pg_session_factory,
        mongo_db=_mongo_db,
        redis_client=_redis_client,
        neo4j_driver=_neo4j_driver,
    )
