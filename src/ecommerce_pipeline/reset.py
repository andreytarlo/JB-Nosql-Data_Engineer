"""
Database reset utilities.

Provided infrastructure — students should not modify this file.

Two functions:
  - reset_all():   DROP+CREATE style wipe — drops tables, collections, keys, nodes.
                   Use before migrate to start fresh.
  - clear_data():  Truncates data but preserves structure (tables, indexes).
                   Used between tests for fast cleanup.
"""

from sqlalchemy import text


def reset_all(engine, mongo_db, redis_client=None, neo4j_driver=None):
    """Drop all database structures and data.

    After calling this, you must run migrate() again to recreate tables/indexes.
    """
    # Import student models so Base.metadata knows about all tables
    import ecommerce_pipeline.postgres_models  # noqa: F401
    from ecommerce_pipeline.postgres_models import Base

    Base.metadata.drop_all(engine)

    for name in mongo_db.list_collection_names():
        mongo_db.drop_collection(name)

    if redis_client:
        redis_client.flushdb()

    if neo4j_driver:
        with neo4j_driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")


def clear_data(engine, mongo_db, redis_client=None, neo4j_driver=None):
    """Truncate all data but preserve database structure.

    Faster than reset_all + migrate — keeps tables, indexes, and constraints intact.
    """
    import ecommerce_pipeline.postgres_models  # noqa: F401
    from ecommerce_pipeline.postgres_models import Base

    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(
                text(f'TRUNCATE TABLE "{table.name}" RESTART IDENTITY CASCADE')
            )
        conn.commit()

    for name in mongo_db.list_collection_names():
        mongo_db[name].delete_many({})

    if redis_client:
        redis_client.flushdb()

    if neo4j_driver:
        with neo4j_driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
