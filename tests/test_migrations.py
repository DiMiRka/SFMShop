import os

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, create_engine, inspect

from sfmshop.core.config import app_settings
from sfmshop.database.models import Base


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
