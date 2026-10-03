"""Shared structs. ``models.py`` holds what becomes a table; everything else is here."""

from __future__ import annotations

from py_common.http import ApiResponse
from pydantic import BaseModel, ConfigDict


class CustomModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class DataResponse[T](ApiResponse):
    """py-common's envelope with a typed ``data`` field, so OpenAPI shows its schema.

    Handlers return a plain dict and let ``response_model`` build this once. Returning
    an instance *and* declaring it as ``response_model`` constructs it twice.
    ``request_id``, ``server_time`` and ``code`` have default factories, so that single
    validation pass fills them in.
    """

    data: T | None = None
