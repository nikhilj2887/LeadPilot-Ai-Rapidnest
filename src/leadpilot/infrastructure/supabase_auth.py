from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from leadpilot.application.auth import AuthenticationError, AuthSession


class SupabaseAuthProvider:
    """Small Supabase Auth boundary; tokens are never persisted in SQLAlchemy."""

    def __init__(
        self,
        url: str,
        anon_key: str,
        *,
        service_role_key: str | None = None,
        timeout: float = 15.0,
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("Supabase URL must be a valid HTTPS URL")
        if not anon_key.strip():
            raise ValueError("Supabase anonymous key is required")
        self._auth_url = f"{url.rstrip('/')}/auth/v1"
        self._anon_key = anon_key
        self._service_role_key = service_role_key
        self._client = httpx.Client(timeout=timeout)

    def sign_in(self, email: str, password: str) -> AuthSession:
        response = self._request(
            "POST",
            "/token?grant_type=password",
            {"email": email, "password": password},
        )
        return self._session(response)

    def refresh(self, refresh_token: str) -> AuthSession:
        response = self._request(
            "POST",
            "/token?grant_type=refresh_token",
            {"refresh_token": refresh_token},
        )
        return self._session(response)

    def sign_out(self, access_token: str) -> None:
        self._request("POST", "/logout", {}, access_token=access_token)

    def request_password_reset(self, email: str, redirect_url: str | None) -> None:
        payload = {"email": email}
        if redirect_url:
            payload["redirect_to"] = redirect_url
        self._request("POST", "/recover", payload)

    def update_password(self, access_token: str, password: str) -> None:
        if len(password) < 10:
            raise AuthenticationError("Password must contain at least 10 characters.")
        self._request("PUT", "/user", {"password": password}, access_token=access_token)

    def invite_user(self, email: str, redirect_url: str | None) -> str:
        if not self._service_role_key:
            raise AuthenticationError(
                "User invitations require a configured Supabase service role key."
            )
        payload = {"email": email}
        if redirect_url:
            payload["redirect_to"] = redirect_url
        data = self._request("POST", "/invite", payload, admin=True)
        user_id = str(data.get("id") or "")
        if not user_id:
            raise AuthenticationError("Supabase did not return an invited user ID.")
        return user_id

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        access_token: str | None = None,
        admin: bool = False,
    ) -> dict[str, Any]:
        key = self._service_role_key if admin else self._anon_key
        headers = {"apikey": key or "", "Content-Type": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        elif admin:
            headers["Authorization"] = f"Bearer {key}"
        try:
            response = self._client.request(
                method, f"{self._auth_url}{path}", json=payload, headers=headers
            )
            response.raise_for_status()
            return response.json() if response.content else {}
        except (httpx.HTTPError, ValueError) as exc:
            message = "Authentication request failed."
            if isinstance(exc, httpx.HTTPStatusError):
                try:
                    body = exc.response.json()
                    message = str(
                        body.get("msg")
                        or body.get("message")
                        or body.get("error_description")
                        or message
                    )
                except ValueError:
                    pass
            raise AuthenticationError(message[:300]) from exc

    @staticmethod
    def _session(data: dict[str, Any]) -> AuthSession:
        user = data.get("user") or {}
        if not all(
            (
                data.get("access_token"),
                data.get("refresh_token"),
                user.get("id"),
                user.get("email"),
            )
        ):
            raise AuthenticationError(
                "Supabase returned an incomplete authentication session."
            )
        return AuthSession(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            expires_at=int(data.get("expires_at") or 0),
            supabase_user_id=str(user["id"]),
            email=str(user["email"]).casefold(),
        )
