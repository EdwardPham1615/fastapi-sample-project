"""Manual spans for the steps auto-instrumentation cannot see.

HTTP in and out, and every SQL statement, are traced already (py-common's
``setup_telemetry``). Add a span here only around a step whose *outcome* is worth
seeing in a trace, such as the sync's report. Both helpers cost nothing while no tracer
provider exists (tests, OTEL__ENABLED=false). Never put a secret, an email, a phone
number or a search term in an attribute: traces outlive the request.
"""

from __future__ import annotations

from contextlib import AbstractContextManager

from opentelemetry import trace
from opentelemetry.trace import Span

_tracer = trace.get_tracer("user-profile-service")


def span(name: str, **attributes: str | int | float | bool) -> AbstractContextManager[Span]:
    """A span that is current inside the ``with``; an exception ends it as an error."""
    return _tracer.start_as_current_span(name, attributes=attributes)


def annotate(**attributes: str | int | float | bool) -> None:
    """Add attributes to the current span (nothing happens when there is none)."""
    current = trace.get_current_span()
    for key, value in attributes.items():
        current.set_attribute(key, value)
