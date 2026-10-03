"""Every struct of the users domain that is not a table."""

from __future__ import annotations

from typing import Self
from uuid import UUID

from py_common.utils import SYSTEM_CLOCK
from pydantic import ConfigDict, EmailStr, Field, field_validator, model_validator

from src.entity import CustomModel
from src.models import epoch_ms
from src.users.constants import Gender, LoginMethod, UserStatus

# ─────────────────────────────────────────────────────────────────────────────
# HTTP contract. Changing anything here can break the mobile app in production:
# it shows up as a diff in docs/openapi.json, and should be reviewed as one.
# ─────────────────────────────────────────────────────────────────────────────


class UserPublic(CustomModel):
    """What an authenticated caller sees."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    oidc_provider_id: str
    first_name: str | None
    last_name: str | None
    middle_name: str | None
    email: EmailStr | None
    phone: str | None
    dial_code: str | None
    gender: Gender
    birth_date: int | None
    status: UserStatus
    lang: str
    logged_in_methods: list[LoginMethod]
    created_at: int
    updated_at: int


class UserCard(CustomModel):
    """What an unauthenticated caller sees.

    A guard decides who gets in; only the response schema decides what leaks out.
    Returning ``UserPublic`` from a public endpoint would expose email, phone and the
    identity-provider subject while looking perfectly guarded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    first_name: str | None
    last_name: str | None


class UserUpdateMe(CustomModel):
    """Fields a user may change on their own profile — and nothing else.

    ``extra="forbid"`` is the barrier against editing identity-provider fields: a
    body carrying ``email`` or ``status`` is a 422, not silently ignored. The fields
    here are ``policy.USER_EDITABLE``: the app-owned ones plus the names, which the
    identity provider only seeds at insert (``logged_in_methods`` is app-owned but
    written by login events, not by the user).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"phone": "912345678", "dial_code": "+84", "gender": 1, "lang": "vi"}]
        },
    )

    first_name: str | None = Field(None, min_length=1, max_length=100)
    last_name: str | None = Field(None, min_length=1, max_length=100)
    middle_name: str | None = Field(None, max_length=100)
    phone: str | None = Field(None, pattern=r"^\d{6,15}$", examples=["912345678"])
    dial_code: str | None = Field(None, pattern=r"^\+\d{1,4}$", examples=["+84"])
    gender: Gender | None = None
    birth_date: int | None = Field(None, description="Epoch ms, 00:00 UTC of the date")
    lang: str | None = Field(None, pattern="^(vi|en)$")

    @field_validator("birth_date")
    @classmethod
    def _not_in_future(cls, value: int | None) -> int | None:
        if value is not None and value > epoch_ms(SYSTEM_CLOCK):
            raise ValueError("birth_date cannot be in the future")
        return value

    @model_validator(mode="after")
    def _at_least_one(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class SyncReport(CustomModel):
    created: int = 0
    updated: int = 0
    unchanged: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Domain entity. Internal — change freely.
# Currently the ORM model `User` in models.py doubles as the entity. If this domain
# ever needs a persistence-free entity, it goes here, a mapper.py appears, and
# sqlalchemy_repository.py subclasses Repository instead of SqlAlchemyRepository.
# Callers do not change: they depend on IUserRepository.
# ─────────────────────────────────────────────────────────────────────────────
