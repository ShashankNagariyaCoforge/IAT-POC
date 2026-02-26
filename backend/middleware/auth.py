"""
JWT authentication middleware.
Validates Azure AD bearer tokens on all /api/* routes.
Public routes: /health, /webhook/* (validated by Graph client state instead).
"""

import logging
from typing import List

import httpx
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import settings

logger = logging.getLogger(__name__)

# Routes that do NOT require JWT auth
PUBLIC_ROUTES: List[str] = [
    "/health",
    "/webhook/",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
]

# Azure AD OpenID Connect config URL
OIDC_CONFIG_URL = f"https://login.microsoftonline.com/{settings.graph_tenant_id}/v2.0/.well-known/openid-configuration"

_jwks_uri: str = ""
_jwks: dict = {}


async def _get_jwks() -> dict:
    """Lazily fetch the JWKS from Azure AD for token validation."""
    global _jwks_uri, _jwks
    if not _jwks:
        async with httpx.AsyncClient() as client:
            config_resp = await client.get(OIDC_CONFIG_URL)
            config_resp.raise_for_status()
            config = config_resp.json()
            _jwks_uri = config["jwks_uri"]
            jwks_resp = await client.get(_jwks_uri)
            jwks_resp.raise_for_status()
            _jwks = jwks_resp.json()
    return _jwks


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates Azure AD JWT tokens on protected routes."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """
        For public routes, pass through. For all others, validate Bearer token.
        """
        path = request.url.path

        # Skip auth for public routes
        if any(path.startswith(pub) for pub in PUBLIC_ROUTES):
            return await call_next(request)

        # Only protect /api/* routes
        if not path.startswith("/api/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header."},
            )

        token = auth_header[len("Bearer "):]
        try:
            await self._validate_token(token)
        except Exception as e:
            logger.warning(f"JWT validation failed: {e}")
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token."},
            )

        return await call_next(request)

    async def _validate_token(self, token: str) -> None:
        """
        Validate JWT token using Azure AD public keys.
        Raises an exception if validation fails.
        """
        import jwt  # PyJWT
        from jwt import PyJWKClient

        jwks_client = PyJWKClient(_jwks_uri or OIDC_CONFIG_URL)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.graph_client_id,
            options={"verify_exp": True},
        )
        logger.debug("JWT token validated successfully.")
