"""Constants and enums owned by the users domain.

Stored as smallint. Values are part of the HTTP contract (the mobile app switches
on them) and of the data at rest — never renumber, only append.
"""

from __future__ import annotations

from enum import IntEnum

USERS_TAG = "users"
USERS_PUBLIC_TAG = "users-public"
INTERNAL_TAG = "internal"


class Gender(IntEnum):
    UNKNOWN = 0
    MALE = 1
    FEMALE = 2
    OTHER = 3


class UserStatus(IntEnum):
    INACTIVE = 0
    ACTIVE = 1
    SUSPENDED = 2
    DELETED = 3


class LoginMethod(IntEnum):
    PASSWORD = 1
    GOOGLE = 2
    APPLE = 3
    FACEBOOK = 4
    OTP = 5


DEFAULT_LANG = "vi"
