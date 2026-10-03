"""A stand-in for Keycloak, served by the app itself in dev. Never mounted outside dev.

It answers at the **paths the real Keycloak uses**, so the production code runs
unchanged against it:

  GET  /realms/{realm}/protocol/openid-connect/certs   ← KeycloakTokenValidator
  POST /realms/{realm}/protocol/openid-connect/token   ← ClientCredentialsTokenProvider
  GET  /admin/realms/{realm}/users                     ← KeycloakAdminClient

plus ``POST /dev/token`` to mint a *user* token for curl or Postman — something the
real Keycloak has no equivalent for, so it lives under /dev and does not pretend to
be a Keycloak path.

Faking at the network boundary instead of faking a dependency is the point: the
validator, JWKS caching, key rotation handling, the service-token provider and the
Admin API client all stay on the executed path. Moving to a real Keycloak is a
change to KEYCLOAK__SERVER_URL, not to code.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import anyio
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import APIRouter, Form, Header, HTTPException, Query, status
from jwt.algorithms import RSAAlgorithm
from py_common.testing.tokens import RsaKeyPair, generate_rsa_keypair, issue_test_token
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.config import Settings

_TOKEN_TTL_SECONDS = 3600


def _load_or_create_keypair(path: Path) -> RsaKeyPair:
    # Persisted so a token minted before a --reload still validates after it.
    if path.exists():
        return RsaKeyPair(**json.loads(path.read_text()))
    keypair = generate_rsa_keypair()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(keypair.__dict__))
    path.chmod(0o600)
    return keypair


class DevTokenRequest(BaseModel):
    sub: str = Field(description="oidc_provider_id of a seeded user")
    scopes: list[str] = Field(default_factory=list)
    expires_in: int = Field(_TOKEN_TTL_SECONDS, ge=60, le=86_400)


def build_fake_keycloak_router(settings: Settings) -> APIRouter:
    kc = settings.keycloak
    keypair = _load_or_create_keypair(Path(settings.dev_keycloak_key_path))
    audience = kc.audience or kc.client_id
    public_key = serialization.load_pem_public_key(keypair.public_pem.encode())
    if not isinstance(public_key, RSAPublicKey):  # generate_rsa_keypair always makes RSA
        raise TypeError("dev Keycloak key is not an RSA key")

    def _mint(sub: str, *, scopes: list[str], expires_in: int, azp: str | None) -> str:
        return issue_test_token(
            keypair,
            issuer=kc.issuer,
            audience=audience,
            sub=sub,
            scopes=scopes,
            expires_in_seconds=expires_in,
            # With KEYCLOAK__ALLOWED_AZP set, a token without azp is rejected — so the
            # fake stamps one, and the azp check runs for real in dev.
            extra_claims={"azp": azp} if azp else None,
        )

    router = APIRouter()
    realm = APIRouter(prefix=f"/realms/{kc.realm}/protocol/openid-connect", include_in_schema=False)

    @realm.get("/certs")
    async def jwks() -> dict[str, Any]:
        jwk = RSAAlgorithm.to_jwk(public_key, as_dict=True)
        return {"keys": [{**jwk, "kid": keypair.kid, "use": "sig", "alg": "RS256"}]}

    @realm.post("/token")
    async def token(
        grant_type: Annotated[str, Form()],
        client_id: Annotated[str, Form()],
        client_secret: Annotated[str, Form()],
        scope: Annotated[str | None, Form()] = None,
    ) -> dict[str, Any]:
        if grant_type != "client_credentials":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported_grant_type")
        if client_id != kc.client_id or client_secret != kc.client_secret:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_client")
        access_token = _mint(
            f"service-account-{client_id}",
            scopes=scope.split() if scope else [],
            expires_in=_TOKEN_TTL_SECONDS,
            azp=client_id,
        )
        return {
            "access_token": access_token,
            "expires_in": _TOKEN_TTL_SECONDS,
            "token_type": "Bearer",
        }

    admin = APIRouter(prefix=f"/admin/realms/{kc.realm}", include_in_schema=False)

    @admin.get("/users")
    async def users(
        authorization: Annotated[str, Header()],
        first: Annotated[int, Query(ge=0)] = 0,
        max_results: Annotated[int, Query(alias="max", ge=1)] = 100,
    ) -> list[dict[str, Any]]:
        scheme, _, bearer = authorization.partition(" ")
        try:
            jwt.decode(bearer, public_key, algorithms=["RS256"], audience=audience)
        except jwt.PyJWTError as exc:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
        if scheme.lower() != "bearer":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bearer token required")
        raw = await anyio.Path(settings.dev_keycloak_users_path).read_text()
        data: list[dict[str, Any]] = json.loads(raw)
        return data[first : first + max_results]

    dev = APIRouter(prefix="/dev", tags=["dev"])

    @dev.post("/token", summary="Mint a user token (dev only)")
    async def dev_token(body: DevTokenRequest) -> dict[str, Any]:
        azp = kc.allowed_azp[0] if kc.allowed_azp else None
        return {
            "access_token": _mint(
                body.sub, scopes=body.scopes, expires_in=body.expires_in, azp=azp
            ),
            "token_type": "Bearer",
            "expires_in": body.expires_in,
        }

    router.include_router(realm)
    router.include_router(admin)
    router.include_router(dev)
    return router
