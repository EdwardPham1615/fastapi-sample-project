"""ORM building blocks shared by every table in this service.

py-common's own ``UUIDv7PrimaryKeyMixin`` and ``TimestampMixin`` do not fit here —
the schema calls for uuid4 keys and bigint epoch-millisecond timestamps rather than
uuid7 and ``timestamptz`` — so the service defines its own. Tables still inherit
``py_common.persistence.Base``: its naming convention is what keeps Alembic
autogenerate producing the same constraint names in every service.
"""

from __future__ import annotations

import uuid

from py_common.utils import SYSTEM_CLOCK, Clock
from sqlalchemy import BigInteger, Uuid
from sqlalchemy.orm import Mapped, mapped_column


def epoch_ms(clock: Clock = SYSTEM_CLOCK) -> int:
    """The time convention of every table here: bigint epoch milliseconds, UTC.

    Lives beside the mixin that defines the convention rather than in a utils
    module of its own. Business code passes an injected clock so tests can use
    ``FixedClock``; the ORM defaults below use the system clock as a safety net.
    """
    return int(clock.now().timestamp() * 1000)


def _now_ms() -> int:
    # Column defaults are called with no arguments (or a context), never a clock.
    return epoch_ms()


class UUIDv4PrimaryKeyMixin:
    # A column default runs at INSERT, not at __init__: User().id is None until the
    # session flushes. Anything that hands ORM objects to an in-memory repository
    # must set the id itself.
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)


class EpochTimestampMixin:
    # No index here: each table declares the one its queries need (users has a
    # composite (created_at, id) index, which also serves created_at alone).
    created_at: Mapped[int] = mapped_column(BigInteger, default=_now_ms, nullable=False)
    updated_at: Mapped[int] = mapped_column(
        BigInteger, default=_now_ms, onupdate=_now_ms, nullable=False
    )
