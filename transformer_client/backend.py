from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request

from transformer_client.models import AuthResponse, MeterDto, RefreshResponse, RegisterDto, TransformerDto


class BackendError(Exception):
    pass


class UnauthorizedError(BackendError):
    pass


@dataclass(slots=True)
class BackendTokens:
    access_token: str | None = None
    refresh_token: str | None = None


class BackendClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.tokens = BackendTokens()

    def set_base_url(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def login(self, email: str, password: str) -> AuthResponse:
        payload = self._request_json(
            "POST",
            "/auth/login",
            {"email": email, "rawPassword": password},
            use_auth=False,
            allow_refresh=False,
        )
        auth = AuthResponse.from_dict(payload)
        self.tokens.access_token = auth.accessToken
        self.tokens.refresh_token = auth.refreshToken
        return auth

    def refresh_access_token(self) -> str:
        if not self.tokens.refresh_token:
            raise UnauthorizedError("Missing refresh token.")
        payload = self._request_json(
            "POST",
            "/auth/refresh",
            {"refreshToken": self.tokens.refresh_token},
            use_auth=False,
            allow_refresh=False,
        )
        refreshed = RefreshResponse.from_dict(payload)
        self.tokens.access_token = refreshed.accessToken
        return refreshed.accessToken

    def get_transformers(self) -> list[TransformerDto]:
        payload = self._request_json("GET", "/transformers")
        return [TransformerDto.from_dict(item) for item in payload]

    def get_meters(self, transformer_id: str) -> list[MeterDto]:
        payload = self._request_json("GET", f"/transformers/{transformer_id}/meters")
        return [MeterDto.from_dict(item) for item in payload]

    def get_registers(self, meter_id: int) -> list[RegisterDto]:
        payload = self._request_json("GET", f"/meters/{meter_id}/registers")
        return [RegisterDto.from_dict(item) for item in payload]

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        use_auth: bool = True,
        allow_refresh: bool = True,
    ) -> Any:
        target = parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if use_auth and self.tokens.access_token:
            headers["Authorization"] = f"Bearer {self.tokens.access_token}"

        req = request.Request(target, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 401 and use_auth and allow_refresh:
                self.refresh_access_token()
                return self._request_json(
                    method,
                    path,
                    payload,
                    use_auth=use_auth,
                    allow_refresh=False,
                )
            if exc.code == 401:
                raise UnauthorizedError(_extract_error_message(exc)) from exc
            raise BackendError(f"HTTP {exc.code}: {_extract_error_message(exc)}") from exc
        except error.URLError as exc:
            raise BackendError(f"Backend connection failed: {exc.reason}") from exc


def _extract_error_message(exc: error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8")
    except Exception:
        return exc.reason if isinstance(exc.reason, str) else "Request failed."
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw or "Request failed."
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if value:
                return str(value)
    return raw or "Request failed."
