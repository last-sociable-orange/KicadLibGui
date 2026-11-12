"""GUI-facing authentication service.

Thin wrapper around :mod:`digikey_auth`: token file management, sign-in URL
generation, callback parsing and token status.  It contains no Tk code so
it can be unit-tested on its own.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

import digikey_auth
from digikey_auth import TokenStatus
from kicad_core.errors import AuthError, AuthRequired


class AuthService:
    def __init__(self, token_path: str | Path):
        self.token_path = Path(token_path)

    # -- state -----------------------------------------------------------

    def load(self) -> dict[str, Any] | None:
        """Return the stored token, or ``None`` when absent/invalid."""
        try:
            return digikey_auth.load_token(self.token_path)
        except (AuthRequired, AuthError):
            return None

    def status(self) -> TokenStatus:
        token = self.load()
        if token is None:
            return digikey_auth.token_status(None)
        return digikey_auth.token_status(token)

    def summary(self) -> str:
        token = self.load()
        if token is None:
            return "Not signed in"
        status = digikey_auth.token_status(token)
        if not status.refresh_valid:
            return "Sign-in expired"
        return status.summary

    def exists(self) -> bool:
        return self.token_path.exists()

    def credentials(self) -> tuple[str, str]:
        """Return the stored Client ID/secret, if a token file exists."""
        token = self.load()
        if not token:
            return "", ""
        return str(token.get("client_id", "")), str(token.get("client_secret", ""))

    # -- sign-in ---------------------------------------------------------

    def build_sign_in(self, client_id: str) -> tuple[str, str]:
        """Return ``(authorization_url, state)`` for the browser step."""
        state = uuid.uuid4().hex
        return digikey_auth.build_authorization_url(client_id, state=state), state

    def complete_sign_in(
        self,
        client_id: str,
        client_secret: str,
        redirect_response: str,
        expected_state: str | None = None,
        *,
        timeout: float = 30,
    ) -> dict[str, Any]:
        """Parse the pasted callback, exchange the code, and save the token."""
        code = digikey_auth.extract_code_from_redirect(
            redirect_response, expected_state=expected_state
        )
        token = digikey_auth.exchange_code(
            client_id, client_secret, code, timeout=timeout
        )
        digikey_auth.save_token(self.token_path, token)
        return token

    def ensure_token(self, *, force_refresh: bool = False, timeout: float = 30) -> dict[str, Any]:
        return digikey_auth.ensure_token(
            self.token_path, force_refresh=force_refresh, timeout=timeout
        )

    # -- maintenance -----------------------------------------------------

    def clear(self) -> None:
        """Remove the token and its lock file; ignore missing files."""
        for path in (self.token_path, self.token_path.with_name(self.token_path.name + ".lock")):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise AuthError("The token file could not be removed.", details=str(exc)) from exc

    def import_legacy(self, source: str | Path) -> Path:
        """Copy an upstream ``.token`` file into the configured location."""
        token = digikey_auth.load_token(source)
        return digikey_auth.save_token(self.token_path, token)
