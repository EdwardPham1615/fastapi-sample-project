"""The service's single ``Auth`` instance.

``Auth`` builds its dependency closures once and FastAPI caches a resolved
dependency per request *keyed on the callable*. So this must stay one module-level
instance: rebuilding it per call would make a request whose router authenticates
it, and whose handler also asks for the claims, decode the token more than once.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from py_common.security import Auth, KeycloakTokenValidator, TokenClaims

from src.config import get_settings

auth = Auth(KeycloakTokenValidator(settings=get_settings().keycloak))

CurrentClaims = Annotated[TokenClaims, Depends(auth.current_user)]
# An absent token gives None; an invalid one still raises 401. Treating a broken
# token as anonymous would hide a broken client (py-common's reasoning, kept).
OptionalClaims = Annotated[TokenClaims | None, Depends(auth.optional_user)]

# Both dependencies also publish the claims on request.state.user (py-common >= 0.3.0),
# which is where RequestContextMiddleware reads the access log's user.id from. No
# binding dependency of our own; tests/test_auth.py checks the log still names the user.
