"""The sync's span carries the report as counts, and nothing personal."""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import src.tracing
from integrations.keycloak.entity import KeycloakUserDTO
from src.users.sync import UserSyncService
from tests.fakes import InMemoryUserRepository


@pytest.fixture
def exporter(monkeypatch: pytest.MonkeyPatch) -> InMemorySpanExporter:
    # A provider of the test's own: the global one can be set only once per process.
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(src.tracing, "_tracer", provider.get_tracer("test"))
    return exporter


async def test_the_sync_span_reports_counts_only(exporter: InMemorySpanExporter) -> None:
    users = [
        KeycloakUserDTO(id="kc-1", username="an", email="an@example.com", first_name="An"),
        KeycloakUserDTO(id="kc-2", username="binh", email="binh@example.com"),
    ]
    repo = InMemoryUserRepository()
    await UserSyncService(repo).apply(users[:1])

    await UserSyncService(repo).apply(users)

    sync = exporter.get_finished_spans()[-1]
    assert sync.name == "users.sync"
    assert dict(sync.attributes or {}) == {"users": 2, "created": 1, "updated": 0, "unchanged": 1}


def test_annotate_without_a_span_does_nothing() -> None:
    src.tracing.annotate(created=1)  # no current span: a no-op, not an error
