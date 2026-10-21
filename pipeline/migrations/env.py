"""Alembic entry point uses the same database configuration as the CLI."""

from alembic import context
from sqlalchemy import create_engine, pool

from notsolazy.config import Settings
from notsolazy.models import Base


def run_migrations() -> None:
    url = Settings().database_url.get_secret_value()
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = create_engine(url, poolclass=pool.NullPool)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
