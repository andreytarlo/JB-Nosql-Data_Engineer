"""
SQLAlchemy ORM models.

Define your database tables here using the SQLAlchemy 2.0 declarative API.
Every class you define here that inherits from Base will become a table
when `Base.metadata.create_all(engine)` is called at startup.

Useful imports are already provided below. Add more as needed.

Documentation:
    https://docs.sqlalchemy.org/en/20/orm/declarative_tables.html
"""

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass
