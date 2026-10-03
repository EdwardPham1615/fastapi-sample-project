"""The two business rules, tested with no app, no database and no clock."""

from __future__ import annotations

import pytest

from integrations.keycloak.entity import KeycloakUserDTO
from src.users import policy
from src.users.constants import UserStatus
from tests.fakes import make_user

NOW = 1_800_000_000_000


def dto(**overrides: object) -> KeycloakUserDTO:
    values: dict[str, object] = {
        "id": "kc-1",
        "username": "an",
        "email": "an@example.com",
        "firstName": "An",
        "lastName": "Nguyen",
        "enabled": True,
        "createdTimestamp": 1_700_000_000_000,
    }
    values.update(overrides)
    return KeycloakUserDTO.model_validate(values)


class TestApplyIdpSnapshot:
    def test_creates_a_user_with_an_explicit_id(self) -> None:
        user, changed = policy.apply_idp_snapshot(None, dto(), now=NOW)
        assert changed
        assert user.id is not None  # the column default would only apply at INSERT
        assert (user.oidc_provider_id, user.first_name, user.email) == (
            "kc-1",
            "An",
            "an@example.com",
        )
        assert user.created_at == 1_700_000_000_000  # Keycloak's own creation time
        assert user.status == UserStatus.ACTIVE

    def test_identity_fields_follow_the_idp(self) -> None:
        user = make_user(oidc_provider_id="kc-1", email="old@example.com", updated_at=1)
        _, changed = policy.apply_idp_snapshot(user, dto(email="new@example.com"), now=NOW)
        assert changed
        assert user.email == "new@example.com"
        assert user.updated_at == NOW

    def test_names_are_seeded_once_then_owned_by_the_app(self) -> None:
        # The middle ownership category: the one that is easy to forget.
        user = make_user(oidc_provider_id="kc-1", email="an@example.com", first_name="Ân")
        _, changed = policy.apply_idp_snapshot(user, dto(firstName="An"), now=NOW)
        assert user.first_name == "Ân"
        assert not changed

    def test_app_owned_fields_are_never_touched(self) -> None:
        user = make_user(
            oidc_provider_id="kc-1", email="an@example.com", phone="912345678", lang="en"
        )
        policy.apply_idp_snapshot(user, dto(), now=NOW)
        assert (user.phone, user.lang) == ("912345678", "en")

    def test_disabled_in_the_idp_means_inactive(self) -> None:
        user = make_user(oidc_provider_id="kc-1", email="an@example.com")
        policy.apply_idp_snapshot(user, dto(enabled=False), now=NOW)
        assert user.status == UserStatus.INACTIVE

    def test_deleted_here_stays_deleted(self) -> None:
        user = make_user(
            oidc_provider_id="kc-1", email="an@example.com", status=int(UserStatus.DELETED)
        )
        _, changed = policy.apply_idp_snapshot(user, dto(enabled=True), now=NOW)
        assert user.status == UserStatus.DELETED
        assert not changed

    def test_no_change_leaves_updated_at_alone(self) -> None:
        user = make_user(oidc_provider_id="kc-1", email="an@example.com", updated_at=5)
        _, changed = policy.apply_idp_snapshot(user, dto(), now=NOW)
        assert not changed
        assert user.updated_at == 5


class TestProfileUpdate:
    def test_applies_user_editable_fields_and_stamps_updated_at(self) -> None:
        user = make_user(updated_at=1)
        policy.apply_profile_update(user, {"phone": "912345678", "first_name": "Ân"}, now=NOW)
        assert (user.phone, user.first_name, user.updated_at) == ("912345678", "Ân", NOW)

    @pytest.mark.parametrize("field", ["email", "status", "oidc_provider_id", "logged_in_methods"])
    def test_refuses_fields_the_user_does_not_own(self, field: str) -> None:
        # Second wall behind the request schema: holds for every caller, not just HTTP.
        with pytest.raises(ValueError, match=field):
            policy.apply_profile_update(make_user(), {field: "x"}, now=NOW)

    @pytest.mark.parametrize(
        ("status", "editable"),
        [
            (UserStatus.ACTIVE, True),
            (UserStatus.INACTIVE, True),
            (UserStatus.SUSPENDED, False),
            (UserStatus.DELETED, False),
        ],
    )
    def test_who_may_edit(self, status: UserStatus, editable: bool) -> None:
        assert policy.can_update_profile(make_user(status=int(status))) is editable


def test_ownership_sets_do_not_overlap() -> None:
    assert not policy.IDP_OWNED & policy.IDP_ON_INSERT_ONLY
    assert not policy.IDP_OWNED & policy.APP_OWNED
    assert not policy.IDP_ON_INSERT_ONLY & policy.APP_OWNED
    assert not policy.USER_EDITABLE & policy.IDP_OWNED


def test_deactivating_a_deleted_user_does_not_resurrect_it() -> None:
    assert (
        policy.next_status_on_deactivate(make_user(status=int(UserStatus.DELETED)))
        == UserStatus.DELETED
    )
    assert policy.next_status_on_deactivate(make_user()) == UserStatus.INACTIVE
