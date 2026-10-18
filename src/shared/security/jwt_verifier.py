from json import JSONDecodeError
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    PyJWKClientConnectionError,
    PyJWKClientError,
)

from src.shared.config import KeycloakSettings


class InvalidAccessTokenError(Exception):
    pass


class JWKSUnavailableError(Exception):
    pass


class JWTVerifier:

    def __init__(
        self,
        settings: KeycloakSettings,
    ):
        self.settings = settings

        self.jwks_client = PyJWKClient(
            uri=settings.jwks_url,
            lifespan=settings.jwks_cache_seconds,
            timeout=settings.jwks_timeout_seconds,
        )

    def verify(
        self,
        token: str,
    ) -> dict[str, Any]:

        try:
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str) or not header["kid"]:
                raise InvalidAccessTokenError()

            signing_key = (
                self.jwks_client.get_signing_key_from_jwt(
                    token
                )
            )

            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.settings.issuer,
                audience=self.settings.jwt_audience,
                options={
                    "require": [
                        "exp",
                        "iat",
                        "iss",
                        "aud",
                        "sub",
                    ]
                },
                leeway=self.settings.jwt_leeway_seconds,
            )

            if (
                claims.get("typ") != "Bearer"
                or not isinstance(claims.get("sub"), str)
                or not claims["sub"].strip()
            ):
                raise InvalidAccessTokenError()

            return claims

        except PyJWKClientConnectionError as exc:
            raise JWKSUnavailableError() from exc

        except (JSONDecodeError, jwt.PyJWKSetError) as exc:
            raise JWKSUnavailableError() from exc

        except (
            jwt.PyJWTError,
            PyJWKClientError,
        ) as exc:
            raise InvalidAccessTokenError() from exc
