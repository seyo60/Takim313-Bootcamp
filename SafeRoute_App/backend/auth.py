"""Supabase access-token verification for FastAPI.

Asymmetric tokens are verified against the project's JWKS. Legacy HS256
tokens are verified by Supabase Auth's `/user` endpoint; the shared signing
secret is never copied into this service.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool

from config import settings


bearer_scheme = HTTPBearer(auto_error=False)
ASYMMETRIC_ALGORITHMS = {"RS256", "ES256", "EdDSA"}


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    role: str
    email: str | None = None


class SupabaseTokenVerifier:
    def __init__(self, project_url: str) -> None:
        self.project_url = project_url.rstrip("/")
        self.issuer = f"{self.project_url}/auth/v1"
        self.jwks = PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_jwk_set=True,
            lifespan=600,
        )

    def verify_asymmetric(self, token: str, algorithm: str) -> dict:
        signing_key = self.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience=settings.supabase_jwt_audience,
            issuer=self.issuer,
            options={"require": ["exp", "iat", "sub", "role"]},
        )

    async def verify_legacy(self, token: str) -> dict:
        if not settings.supabase_publishable_key:
            raise ValueError("Supabase publishable key is not configured")
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as client:
            response = await client.get(
                f"{self.issuer}/user",
                headers={
                    "apikey": settings.supabase_publishable_key,
                    "Authorization": f"Bearer {token}",
                },
            )
        response.raise_for_status()
        user = response.json()
        return {
            "sub": user["id"],
            "email": user.get("email"),
            "role": "authenticated",
        }


@lru_cache(maxsize=2)
def _verifier(project_url: str) -> SupabaseTokenVerifier:
    return SupabaseTokenVerifier(project_url)


async def _authenticate_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> AuthenticatedUser | None:
    if credentials is None:
        return None
    if credentials.scheme.casefold() != "bearer" or not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Geçersiz oturum.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    try:
        header = jwt.get_unverified_header(token)
        algorithm = str(header.get("alg", ""))
        verifier = _verifier(settings.supabase_url)
        if algorithm in ASYMMETRIC_ALGORITHMS:
            claims = await run_in_threadpool(
                verifier.verify_asymmetric,
                token,
                algorithm,
            )
        elif algorithm == "HS256":
            claims = await verifier.verify_legacy(token)
        else:
            raise ValueError("Unsupported token algorithm")

        role = str(claims.get("role", ""))
        if role != "authenticated":
            raise ValueError("Token role is not authenticated")
        return AuthenticatedUser(
            user_id=UUID(str(claims["sub"])),
            role=role,
            email=claims.get("email"),
        )
    except (ValueError, KeyError, jwt.PyJWTError, httpx.HTTPError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum doğrulanamadı.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser | None:
    """Kimlik bilgisi yoksa None döner; anonim topluluk ihbarı için."""
    return await _authenticate_credentials(credentials)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser | None:
    if credentials is None:
        if settings.auth_required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Oturum gerekli.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None
    return await _authenticate_credentials(credentials)


async def require_current_user(
    user: AuthenticatedUser | None = Depends(get_current_user),
) -> AuthenticatedUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum gerekli.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
