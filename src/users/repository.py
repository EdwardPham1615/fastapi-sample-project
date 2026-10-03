"""The users domain's data contract — the only repository symbol other domains may import.

Kept apart from ``sqlalchemy_repository.py`` so that "depend on the interface, not
the implementation" is checkable: tests/test_boundaries.py fails any module other
than the composition points that imports the concrete class.

An ABC, not a ``Protocol``: py-common's ``Repository`` is an ABC, and a Protocol
cannot inherit from one (``TypeError: Protocols can only inherit from other
protocols``). Implementations therefore inherit this explicitly — which is stronger
anyway: a missing method fails at instantiation instead of passing silently.
"""

from __future__ import annotations

from abc import abstractmethod
from uuid import UUID

from py_common.http.pagination import Page
from py_common.persistence import Repository

from src.exceptions import UserNotFound
from src.users.constants import UserStatus
from src.users.models import User


class IUserRepository(Repository[User, UUID]):
    @abstractmethod
    async def get_by_oidc_id(self, oidc_provider_id: str) -> User | None: ...

    @abstractmethod
    async def search(
        self, *, status: UserStatus | None, q: str | None, limit: int, offset: int
    ) -> Page[User]:
        """Returns py-common's ``Page``, not a ``Select``, so an in-memory fake can
        implement it without SQLAlchemy."""

    async def get_existing(self, user_id: UUID) -> User:
        """Load a user or raise not-found — the one definition of "exists" for users.

        Built on py-common's ``get_or_raise`` and concrete, like it, so every
        implementation (the in-memory fake included) inherits the rule unchanged. The
        HTTP loader and the gRPC servicer both call this; neither restates the rule.

        A DELETED user raises exactly what a missing one does, so the response cannot
        tell a caller that the id was once valid (tests/test_loaders.py compares them).
        """
        user = await self.get_or_raise(user_id, detail=UserNotFound.DETAIL)
        if user.status == UserStatus.DELETED:
            raise UserNotFound()
        return user
