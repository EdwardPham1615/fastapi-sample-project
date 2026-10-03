"""The one place a unit of work is opened for an HTTP request.

py-common's ``UnitOfWork`` spans exactly one engine, so two domains writing in the
same request must share one session or they commit separately. Nothing below the
route layer opens a session of its own; they all receive this one.

What makes that hold is FastAPI caching a resolved dependency per request:
``Depends(get_uow)`` reached from two different domains resolves to the same
object. That is why this is a dependency rather than a context manager each module
opens for itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from py_common.persistence import SqlAlchemyUnitOfWork


async def get_uow(request: Request) -> AsyncIterator[SqlAlchemyUnitOfWork]:
    # Commits on a clean exit, rolls back if the handler raises.
    async with SqlAlchemyUnitOfWork(request.app.state.session_factory) as uow:
        yield uow


UowDep = Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)]
