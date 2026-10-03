"""SQLAlchemy implementation of ``IUserRepository``.

Only composition points import this module (``deps.py``, the gRPC servicer, and
scripts); everything else depends on ``repository.IUserRepository``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from py_common.http.pagination import Page
from py_common.persistence import SqlAlchemyRepository, paginate_offset
from sqlalchemy import or_, select

from src.users.constants import UserStatus
from src.users.models import User
from src.users.repository import IUserRepository


class UserRepository(SqlAlchemyRepository[User, UUID], IUserRepository):
    model = User
    # created_at alone is not unique; id breaks ties so pages are stable.
    _default_order_by: Any = (User.created_at.desc(), User.id.desc())

    async def get_by_oidc_id(self, oidc_provider_id: str) -> User | None:
        stmt = select(User).where(User.oidc_provider_id == oidc_provider_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def search(
        self, *, status: UserStatus | None, q: str | None, limit: int, offset: int
    ) -> Page[User]:
        # Offset pagination only: uuid4 keys are random and created_at is not
        # unique, so no column is both unique and sortable for a cursor.
        stmt = select(User).order_by(*self._default_order_by)
        if status is not None:
            stmt = stmt.where(User.status == int(status))
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like))
            )
        return await paginate_offset(self.session, stmt, limit=limit, offset=offset)
