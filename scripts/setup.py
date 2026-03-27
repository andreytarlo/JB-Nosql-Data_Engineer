"""
Full setup: reset + migrate + seed in one command.

Usage:
    uv run python -m scripts.setup

This is a convenience wrapper. It is equivalent to running:
    uv run python -m scripts.migrate
    uv run python -m scripts.seed

Provided infrastructure — students should not modify this file.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _pg_url() -> str:
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "ecommerce")
    user = os.environ.get("POSTGRES_USER", "postgres")
    pwd = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


def _mongo_db():
    from pymongo import MongoClient

    host = os.environ.get("MONGO_HOST", "localhost")
    port = int(os.environ.get("MONGO_PORT", "27017"))
    db = os.environ.get("MONGO_DB", "ecommerce")
    return MongoClient(host, port)[db]


def _redis_client():
    host = os.environ.get("REDIS_HOST")
    if not host:
        return None
    import redis

    port = int(os.environ.get("REDIS_PORT", "6379"))
    return redis.Redis(host=host, port=port, decode_responses=True)


def _neo4j_driver():
    host = os.environ.get("NEO4J_HOST")
    pwd = os.environ.get("NEO4J_PASSWORD")
    if not host or not pwd:
        return None
    from neo4j import GraphDatabase

    port = os.environ.get("NEO4J_BOLT_PORT", "7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    return GraphDatabase.driver(f"bolt://{host}:{port}", auth=(user, pwd))


def main():
    from sqlalchemy import create_engine

    from ecommerce_pipeline.reset import reset_all
    from scripts.migrate import migrate
    from scripts.seed import seed

    engine = create_engine(_pg_url(), echo=False)
    mongo_db = _mongo_db()
    redis_client = _redis_client()
    neo4j_driver = _neo4j_driver()

    print("Step 1/3: Resetting all databases...")
    reset_all(engine, mongo_db, redis_client, neo4j_driver)

    print("Step 2/3: Running migration...")
    migrate(engine, mongo_db, redis_client, neo4j_driver)

    print("Step 3/3: Seeding data...")
    seed(engine, mongo_db, redis_client, neo4j_driver)

    print("\nDone! Start the API with:")
    print("  uv run uvicorn ecommerce_pipeline.api.app:app --reload")

    if neo4j_driver:
        neo4j_driver.close()
    engine.dispose()


if __name__ == "__main__":
    main()
