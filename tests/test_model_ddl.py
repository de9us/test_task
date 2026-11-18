from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import insert

from payment_service.models import Base, OutboxEvent, Payment


def test_required_tables_exist():
    assert set(Base.metadata.tables) == {"payments", "outbox"}
    assert Payment.__table__.c["amount"].type.scale == 2
    assert Payment.__table__.c["metadata"].type.__class__.__name__ == "JSONB"
    assert not Payment.__table__.c["idempotency_key"].nullable
    assert OutboxEvent.__table__.c["published_at"].nullable


def test_core_postgresql_insert_supports_mapped_metadata_attribute():
    stmt = insert(Payment).values(metadata_={"order": 7}, description="order")
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "metadata" in sql
    assert "INSERT INTO payments" in sql


def test_outbox_partial_index_exists():
    index = next(iter(OutboxEvent.__table__.indexes))
    assert index.name == "ix_outbox_unpublished_due"
    assert "published_at IS NULL" in str(index.dialect_options["postgresql"]["where"])
