"""Named errors, rendered as problem+json by py-common's ``AppError`` handler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from py_common.errors import AppError, ErrorCode
from py_common.http.problem import app_error_handler, unhandled_exception_handler
from py_common.logging import get_logger

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import JSONResponse

logger = get_logger(__name__)


class UserNotFound(AppError):
    DETAIL = "User not found"

    def __init__(self) -> None:
        super().__init__(self.DETAIL, error_code=ErrorCode.NOT_FOUND)


class ProfileNotSynced(AppError):
    def __init__(self) -> None:
        super().__init__(
            "Profile has not been synced from the identity provider yet",
            error_code=ErrorCode.NOT_FOUND,
        )


class ProfileNotEditable(AppError):
    def __init__(self) -> None:
        super().__init__(
            "Profile is not editable in its current status",
            error_code=ErrorCode.FORBIDDEN,
        )


def is_unique_violation(exc: BaseException) -> bool:
    """True only for SQLSTATE 23505. Other integrity errors — NOT NULL, foreign key,
    check — are bugs, not conflicts, and must stay 500s."""
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    return sqlstate == "23505"


async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """A duplicate is the caller's problem (409); anything else is ours (500).

    The detail stays generic: constraint names describe the schema, and a 409 body
    can reach the mobile app. The constraint is logged instead.
    """
    if is_unique_violation(exc):
        logger.info("unique_violation", constraint=str(getattr(exc, "orig", exc)))
        return await app_error_handler(
            request, AppError.conflict("A record with the same unique value already exists")
        )
    return await unhandled_exception_handler(request, exc)
