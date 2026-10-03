"""The ``users`` table — a local projection of identities that live in Keycloak.

Which columns Keycloak owns and which this service owns is decided in
``policy.py``, not here.
"""

from __future__ import annotations

from py_common.persistence import Base
from sqlalchemy import JSON, BigInteger, Index, SmallInteger, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from src.models import EpochTimestampMixin, UUIDv4PrimaryKeyMixin
from src.users.constants import DEFAULT_LANG, Gender, UserStatus


class User(Base, UUIDv4PrimaryKeyMixin, EpochTimestampMixin):
    __tablename__ = "users"

    oidc_provider_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    dial_code: Mapped[str | None] = mapped_column(String(8))
    gender: Mapped[int] = mapped_column(SmallInteger, default=Gender.UNKNOWN, nullable=False)
    # Epoch milliseconds of 00:00 UTC on the date of birth.
    birth_date: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[int] = mapped_column(
        SmallInteger, default=UserStatus.ACTIVE, nullable=False, index=True
    )
    lang: Mapped[str] = mapped_column(String(10), default=DEFAULT_LANG, nullable=False)
    # smallint[] in Postgres. The JSON variant exists only so the SQLite unit suite
    # can create the table — which also means that suite does NOT test the real
    # column type; tests/integration does.
    # SQLAlchemy does not see in-place mutation of this list: assign a new list,
    # never .append().
    logged_in_methods: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger).with_variant(JSON(), "sqlite"), default=list, nullable=False
    )

    __table_args__ = (Index("ix_users_created_at_id", "created_at", "id"),)
