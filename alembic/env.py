"""Alembic environment: stock layout plus two additions.

1. The URL comes from the service settings, not alembic.ini.
2. New revisions are numbered 000001, 000002, ... instead of random hex ids.
"""

from __future__ import annotations

from typing import Any

from alembic import context
from alembic.script import ScriptDirectory
from py_common.persistence import Base
from sqlalchemy import engine_from_config, pool

import src.users.models  # noqa: F401 — registers the tables on Base.metadata
from src.config import get_settings

config = context.config

# An explicitly set URL wins — the integration suite points Alembic at the *_test
# database this way. Otherwise the service settings decide.
if not config.get_main_option("sqlalchemy.url"):
    # configparser treats % as interpolation; percent-encoded credentials in the DSN
    # would otherwise make every migration command fail. Same fix as py-common's
    # build_alembic_config.
    config.set_main_option("sqlalchemy.url", get_settings().postgres.sync_dsn.replace("%", "%%"))

target_metadata = Base.metadata


def _sequential_rev_id(context_: Any, revision: Any, directives: list[Any]) -> None:
    """rev_id = highest existing number + 1, zero-padded to 6 digits.

    Two branches both creating 000002 collide loudly when merged — Alembic refuses a
    duplicate revision — which is the point: random ids would silently produce two
    heads instead. Whoever merges second renumbers. tests/test_migrations.py checks
    there is one head and that the numbers follow the down_revision chain.
    """
    if not directives:
        return
    script_dir = ScriptDirectory.from_config(context_.config)
    numbers = [int(rev.revision) for rev in script_dir.walk_revisions() if rev.revision.isdigit()]
    directives[0].rev_id = f"{max(numbers, default=0) + 1:06d}"


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=_sequential_rev_id,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=_sequential_rev_id,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
