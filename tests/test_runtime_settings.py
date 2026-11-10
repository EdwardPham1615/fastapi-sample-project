"""Outside dev, the app refuses to start on a dev value of any secret in .env.example
(or py-common's default), and the error names the variable, never the value."""

from __future__ import annotations

from pathlib import Path

import pytest
from dotenv import dotenv_values
from py_common.config import Environment

from src.config import Settings, check_runtime_settings

EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"

# The env var of each checked secret, and where it sits in Settings.
SECRETS = {
    "HTTP__INTERNAL_API_KEY": ("http", "internal_api_key"),
    "POSTGRES__PASSWORD": ("postgres", "password"),
    "KEYCLOAK__CLIENT_SECRET": ("keycloak", "client_secret"),
}


def _settings(base: Settings, environment: str = "staging", **values: str) -> Settings:
    """``base`` with real-looking secrets, then ``values`` spoiling some of them."""
    real = {name: name[0].lower() * 40 for name in SECRETS}
    groups: dict[str, dict[str, str]] = {}
    for name, value in (real | values).items():
        group, field = SECRETS[name]
        groups.setdefault(group, {})[field] = value
    update = {g: getattr(base, g).model_copy(update=f) for g, f in groups.items()}
    # model_copy: building Settings(environment=...) would clash with ENVIRONMENT=dev
    # set by conftest. It skips validation, so pass the enum: is_dev compares by `is`.
    return base.model_copy(update={"environment": Environment(environment), **update})


def test_real_values_pass(settings: Settings) -> None:
    check_runtime_settings(_settings(settings))


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_every_dev_value_of_the_example_is_refused_outside_dev(
    settings: Settings, name: str
) -> None:
    value = dotenv_values(EXAMPLE).get(name)
    assert value, f"{name} has no value in .env.example"
    with pytest.raises(RuntimeError, match=name) as refused:
        check_runtime_settings(_settings(settings, **{name: value}))
    assert value not in str(refused.value)  # names only, never the value


def test_py_common_default_password_is_refused_outside_dev(settings: Settings) -> None:
    default = Settings.model_fields["postgres"].default_factory().password  # type: ignore[call-arg, misc]
    with pytest.raises(RuntimeError, match="POSTGRES__PASSWORD"):
        check_runtime_settings(_settings(settings, POSTGRES__PASSWORD=default))


def test_every_secret_of_the_example_is_checked() -> None:
    names = {
        k
        for k, v in dotenv_values(EXAMPLE).items()
        if v and any(word in k for word in ("SECRET", "PASSWORD", "API_KEY"))
    }
    assert names <= set(SECRETS)


def test_dev_keeps_its_dev_values(settings: Settings) -> None:
    values = {name: dotenv_values(EXAMPLE)[name] or "" for name in SECRETS}
    check_runtime_settings(_settings(settings, "dev", **values))
