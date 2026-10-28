import os

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, inspect

from sfmshop.core.config import app_settings
from sfmshop.database.models import EMBEDDING_DIMENSIONS, Base


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_MIGRATION_TESTS"),
    reason="нужен PostgreSQL после alembic upgrade head (в CI задаётся RUN_MIGRATION_TESTS=1)",
)


def model_constraint_names(kind):
    result = {}
    for table in Base.metadata.sorted_tables:
        constraints = [*table.constraints, *(c for column in table.columns for c in column.constraints)]
        names = {c.name for c in constraints if isinstance(c, kind) and isinstance(c.name, str)}
        if names:
            result[table.name] = names
    return result


@pytest.fixture(scope="module")
def inspector():
    engine = create_engine(app_settings.sync_postgres_url)
    yield inspect(engine)
    engine.dispose()


def test_named_check_constraints_from_models_exist_in_migrated_database(inspector):
    expected = model_constraint_names(CheckConstraint)
    assert expected

    for table, names in expected.items():
        actual = {c["name"] for c in inspector.get_check_constraints(table)}
        assert names <= actual, f"{table}: в миграциях нет {sorted(names - actual)}"


def test_named_unique_constraints_from_models_exist_in_migrated_database(inspector):
    for table, names in model_constraint_names(UniqueConstraint).items():
        actual = {c["name"] for c in inspector.get_unique_constraints(table)}
        assert names <= actual, f"{table}: в миграциях нет {sorted(names - actual)}"


def test_products_name_has_trigram_gin_index(inspector):
    [index] = [i for i in inspector.get_indexes("products") if i["name"] == "ix_products_name_trgm"]

    assert index["column_names"] == ["name"]
    assert index["dialect_options"]["postgresql_using"] == "gin"
    assert index["dialect_options"]["postgresql_ops"] == {"name": "gin_trgm_ops"}


def test_product_embeddings_have_hnsw_cosine_index(inspector):
    [index] = [i for i in inspector.get_indexes("product_embeddings")
               if i["name"] == "ix_product_embeddings_embedding_hnsw"]

    assert index["column_names"] == ["embedding"]
    assert index["dialect_options"]["postgresql_using"] == "hnsw"
    assert index["dialect_options"]["postgresql_ops"] == {"embedding": "vector_cosine_ops"}


def test_product_embedding_column_matches_model_dimensions(inspector):
    [column] = [c for c in inspector.get_columns("product_embeddings") if c["name"] == "embedding"]

    assert column["type"].dim == EMBEDDING_DIMENSIONS
