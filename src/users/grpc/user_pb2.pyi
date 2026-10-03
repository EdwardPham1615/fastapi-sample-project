from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message

DESCRIPTOR: _descriptor.FileDescriptor

class GetProfileRequest(_message.Message):
    __slots__ = ("user_id",)
    USER_ID_FIELD_NUMBER: _ClassVar[int]
    user_id: str
    def __init__(self, user_id: str | None = ...) -> None: ...

class UserProfile(_message.Message):
    __slots__ = (
        "email",
        "first_name",
        "id",
        "last_name",
        "oidc_provider_id",
        "status",
        "updated_at",
    )
    ID_FIELD_NUMBER: _ClassVar[int]
    OIDC_PROVIDER_ID_FIELD_NUMBER: _ClassVar[int]
    FIRST_NAME_FIELD_NUMBER: _ClassVar[int]
    LAST_NAME_FIELD_NUMBER: _ClassVar[int]
    EMAIL_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    oidc_provider_id: str
    first_name: str
    last_name: str
    email: str
    status: int
    updated_at: int
    def __init__(
        self,
        id: str | None = ...,
        oidc_provider_id: str | None = ...,
        first_name: str | None = ...,
        last_name: str | None = ...,
        email: str | None = ...,
        status: int | None = ...,
        updated_at: int | None = ...,
    ) -> None: ...
