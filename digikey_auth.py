"""DigiKey OAuth2 helpers used by the CLI, the services and the GUI.

This module replaces upstream ``digikey_auth.py``'s interactive-only code
with importable functions.  The command-line interface is preserved at the
bottom of the file (``python digikey_auth.py -u ID -s SECRET``).

Security notes
--------------
* Token files keep the exact upstream JSON shape so an existing ``.token``
  file can be imported unchanged.
* Writes are atomic (temp file + :func:`os.replace`) and use mode ``0600``
  on POSIX, so a crash cannot truncate the file.
* Tokens and client secrets are never printed or logged by the helpers.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
import time
import urllib.parse
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from kicad_core.errors import AuthError, AuthRequired

AUTHORIZATION_BASE_URL = "https://api.digikey.com/v1/oauth2/authorize"
TOKEN_URL = "https://api.digikey.com/v1/oauth2/token"
REDIRECT_URI = "https://localhost:8000/oauth2/callback"

#: Refresh just before the access token expires.
TOKEN_REFRESH_MARGIN_SECONDS = 30

#: DigiKey refresh tokens are long lived; used only when the API omits the field.
DEFAULT_REFRESH_TOKEN_LIFETIME = 90 * 24 * 60 * 60

TOKEN_KEYS = (
    "client_id",
    "client_secret",
    "access_token",
    "refresh_token",
    "expires_by",
    "refresh_token_expires_by",
)


@dataclass(frozen=True)
class TokenStatus:
    present: bool
    access_valid: bool
    refresh_valid: bool
    access_expires_in: int
    refresh_expires_in: int

    @property
    def days_remaining(self) -> int:
        return max(0, int(math.ceil(self.access_expires_in / 86400)))

    @property
    def summary(self) -> str:
        if not self.present:
            return "Not signed in"
        if not self.refresh_valid:
            return "Sign-in expired"
        if self.access_expires_in <= 0:
            return "Token expired"
        if self.access_expires_in <= 60:
            return "Token expires in <1 min"
        if self.access_expires_in < 86400:
            hours = int(math.ceil(self.access_expires_in / 3600))
            return f"Token valid - expires in {hours} h"
        days = self.days_remaining
        return f"Token valid - expires in {days} day{'s' if days != 1 else ''}"


# ---------------------------------------------------------------------------
# Token file I/O
# ---------------------------------------------------------------------------


def _now(now: float | None = None) -> int:
    return int(time.time() if now is None else now)


def load_token(path: str | Path) -> dict[str, Any]:
    """Load and validate a token file.

    Raises :class:`AuthRequired` when no token exists and :class:`AuthError`
    when the file is unreadable or incomplete.
    """
    token_path = Path(path)
    if not token_path.exists():
        raise AuthRequired(
            "No DigiKey token found. Sign in with your DigiKey app credentials."
        )
    try:
        with token_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise AuthError("The DigiKey token file could not be read.", details=str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise AuthError(
            "The DigiKey token file is not valid JSON.", details=str(exc)
        ) from exc
    if not isinstance(data, dict):
        raise AuthError("The DigiKey token file has an unexpected format.")
    missing = [key for key in TOKEN_KEYS if key not in data]
    if missing:
        raise AuthError(
            "The DigiKey token file is incomplete.",
            details="Missing fields: " + ", ".join(missing),
        )
    return data


def _atomic_write_json(path: Path, data: Mapping[str, Any], *, private: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        if private and os.name != "nt":
            os.chmod(temp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(data), handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        if private and os.name != "nt":
            os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def save_token(path: str | Path, token: Mapping[str, Any]) -> Path:
    """Atomically persist a token dict, preserving the upstream key names."""
    token_path = Path(path)
    payload = {key: token[key] for key in TOKEN_KEYS}
    try:
        _atomic_write_json(token_path, payload, private=True)
    except OSError as exc:
        raise AuthError("The DigiKey token file could not be saved.", details=str(exc)) from exc
    return token_path


@contextmanager
def _token_lock(path: Path) -> Iterator[None]:
    """Best-effort inter-process lock next to the token file."""
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = None
    try:
        handle = open(lock_path, "a+b")
        if os.name == "nt":  # pragma: no cover - exercised on Windows only
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:  # pragma: no cover - exercised on POSIX only
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if handle is not None:
            try:
                if os.name == "nt":  # pragma: no cover
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:  # pragma: no cover
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (OSError, ValueError):
                pass
            handle.close()


def token_status(token: Mapping[str, Any] | None, *, now: float | None = None) -> TokenStatus:
    """Describe the validity of a token dict (``None`` means no token)."""
    if not token:
        return TokenStatus(False, False, False, 0, 0)
    current = _now(now)
    try:
        access_left = int(token.get("expires_by", 0)) - current
        refresh_left = int(token.get("refresh_token_expires_by", 0)) - current
    except (TypeError, ValueError):
        return TokenStatus(True, False, False, 0, 0)
    return TokenStatus(
        present=True,
        access_valid=access_left > TOKEN_REFRESH_MARGIN_SECONDS,
        refresh_valid=refresh_left > TOKEN_REFRESH_MARGIN_SECONDS,
        access_expires_in=access_left,
        refresh_expires_in=refresh_left,
    )


# ---------------------------------------------------------------------------
# OAuth2 flow
# ---------------------------------------------------------------------------


def build_authorization_url(
    client_id: str,
    redirect_uri: str = REDIRECT_URI,
    state: str | None = None,
) -> str:
    """Build the URL the user opens in a browser."""
    if not client_id or not client_id.strip():
        raise AuthError("Enter your DigiKey Client ID first.")
    params = {
        "response_type": "code",
        "client_id": client_id.strip(),
        "redirect_uri": redirect_uri,
    }
    if state:
        params["state"] = state
    return f"{AUTHORIZATION_BASE_URL}?{urllib.parse.urlencode(params)}"


def extract_code_from_redirect(
    redirect_response: str, expected_state: str | None = None
) -> str:
    """Extract ``code`` from the URL the browser failed to open.

    Accepts the full ``https://localhost:8000/oauth2/callback?...`` URL, a
    bare query string, or a bare authorization code.  A provided ``state``
    must match ``expected_state``; a missing state is tolerated because some
    users trim the URL when copying.
    """
    text = (redirect_response or "").strip()
    if not text:
        raise AuthError("Paste the URL from your browser's address bar.")

    query = ""
    if text.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(text)
        query = parsed.query
    elif "code=" in text:
        query = text.split("?", 1)[-1]

    if query:
        params = urllib.parse.parse_qs(query)
        error = params.get("error", [""])[0]
        if error:
            description = params.get("error_description", [""])[0]
            raise AuthError(
                f"DigiKey returned an authorization error: {error}"
                + (f" - {description}" if description else "")
            )
        if expected_state and "state" in params:
            if params["state"][0] != expected_state:
                raise AuthError(
                    "The sign-in response does not match this sign-in attempt "
                    "(state mismatch). Open the sign-in page again and retry."
                )
        if params.get("code"):
            return params["code"][0]
        raise AuthError(
            "The pasted URL has no 'code' parameter. Copy the full "
            "https://localhost:8000/oauth2/callback?... URL."
        )

    # A bare code (no '?' and no '=') is accepted for convenience.
    if "=" not in text and "/" not in text and len(text) < 4096:
        return text
    raise AuthError(
        "That does not look like the DigiKey callback URL. Paste the full "
        "https://localhost:8000/oauth2/callback?... URL."
    )


def _post_token_request(data: Mapping[str, str], timeout: float) -> dict[str, Any]:
    try:
        response = requests.post(
            TOKEN_URL,
            data=dict(data),
            headers={"Accept": "application/json"},
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise AuthError(
            "DigiKey did not answer in time. Check your network and retry.",
            details=str(exc),
        ) from exc
    except requests.RequestException as exc:
        raise AuthError(
            "Could not reach DigiKey to complete sign-in.",
            details=str(exc),
        ) from exc

    if response.status_code != 200:
        error_code = ""
        description = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                error_code = str(payload.get("error", "") or "")
                description = str(payload.get("error_description", "") or "")
        except ValueError:
            description = (response.text or "")[:300]
        message = "DigiKey rejected the sign-in request."
        if error_code == "invalid_grant":
            message = "That sign-in code is invalid or has already been used. Try again."
        elif error_code == "invalid_client":
            message = "DigiKey rejected the Client ID or Client secret."
        elif response.status_code >= 500:
            message = "DigiKey is temporarily unavailable. Retry in a moment."
        raise AuthError(
            message,
            details=f"HTTP {response.status_code} {error_code} {description}".strip(),
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise AuthError(
            "DigiKey returned an unexpected token response.", details=str(exc)
        ) from exc
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise AuthError("DigiKey returned an unexpected token response.")
    return payload


def _normalise_token(
    payload: Mapping[str, Any],
    *,
    client_id: str,
    client_secret: str,
    now: float | None = None,
) -> dict[str, Any]:
    current = _now(now)
    try:
        expires_in = int(payload.get("expires_in", 0))
    except (TypeError, ValueError):
        expires_in = 0
    try:
        refresh_lifetime = int(
            payload.get("refresh_token_expires_in", DEFAULT_REFRESH_TOKEN_LIFETIME)
        )
    except (TypeError, ValueError):
        refresh_lifetime = DEFAULT_REFRESH_TOKEN_LIFETIME
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "access_token": str(payload["access_token"]),
        "refresh_token": str(payload.get("refresh_token", "")),
        "expires_by": current + expires_in,
        "refresh_token_expires_by": current + refresh_lifetime,
    }


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = REDIRECT_URI,
    *,
    timeout: float = 30,
    now: float | None = None,
) -> dict[str, Any]:
    """Exchange an authorization code for a token dict."""
    if not client_id.strip() or not client_secret:
        raise AuthError("Enter both the DigiKey Client ID and Client secret.")
    if not code.strip():
        raise AuthError("Paste the callback URL from your browser.")
    payload = _post_token_request(
        {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "redirect_uri": redirect_uri,
            "client_id": client_id.strip(),
            "client_secret": client_secret,
        },
        timeout,
    )
    return _normalise_token(
        payload, client_id=client_id.strip(), client_secret=client_secret, now=now
    )


def refresh_token_request(
    client_id: str,
    client_secret: str,
    refresh_token: str,
    *,
    timeout: float = 30,
    now: float | None = None,
) -> tuple[dict[str, Any], int]:
    """Refresh a token; returns ``(normalised token, expires_in)``."""
    if not client_id.strip() or not client_secret:
        raise AuthError("The stored DigiKey Client ID or secret is missing.")
    payload = _post_token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id.strip(),
            "client_secret": client_secret,
        },
        timeout,
    )
    normalised = _normalise_token(
        payload, client_id=client_id.strip(), client_secret=client_secret, now=now
    )
    try:
        expires_in = int(payload.get("expires_in", 0))
    except (TypeError, ValueError):
        expires_in = 0
    return normalised, expires_in


def refresh_access_token(
    client_id: str, client_secret: str, refresh_token: str, **kwargs: Any
) -> tuple[str, str, int, int]:
    """Upstream-compatible refresh helper returning the four-tuple."""
    token, expires_in = refresh_token_request(
        client_id, client_secret, refresh_token, **kwargs
    )
    now = _now(kwargs.get("now"))
    refresh_lifetime = max(0, int(token["refresh_token_expires_by"]) - now)
    return token["access_token"], token["refresh_token"], expires_in, refresh_lifetime


def get_access_token(
    auth_code: str, client_id: str, client_secret: str
) -> tuple[str, str, int, int]:
    """Upstream-compatible code exchange returning the four-tuple."""
    token = exchange_code(client_id, client_secret, auth_code)
    now = _now()
    return (
        token["access_token"],
        token["refresh_token"],
        max(0, int(token["expires_by"]) - now),
        max(0, int(token["refresh_token_expires_by"]) - now),
    )


def ensure_token(
    path: str | Path,
    *,
    force_refresh: bool = False,
    timeout: float = 30,
    now: float | None = None,
) -> dict[str, Any]:
    """Return a usable token, refreshing it atomically when needed.

    Raises :class:`AuthRequired` when the user must sign in again.
    """
    token = load_token(path)
    status = token_status(token, now=now)
    if status.access_valid and not force_refresh:
        return token
    if not status.refresh_valid:
        raise AuthRequired("DigiKey session expired. Sign in again.")

    token_path = Path(path)
    with _token_lock(token_path):
        # Another process may have refreshed while we waited for the lock.
        token = load_token(token_path)
        status = token_status(token, now=now)
        if status.access_valid and not force_refresh:
            return token
        if not status.refresh_valid:
            raise AuthRequired("DigiKey session expired. Sign in again.")
        refreshed, _expires_in = refresh_token_request(
            str(token["client_id"]),
            str(token["client_secret"]),
            str(token["refresh_token"]),
            timeout=timeout,
            now=now,
        )
        save_token(token_path, refreshed)
        return refreshed


# ---------------------------------------------------------------------------
# Interactive CLI (upstream behaviour)
# ---------------------------------------------------------------------------


def get_auth_code(client_id: str, client_secret: str) -> str:
    """Prompt the user for the callback URL (interactive CLI only)."""
    state = uuid.uuid4().hex
    url = build_authorization_url(client_id, REDIRECT_URI, state=state)
    print("Open this URL, sign in, and paste the localhost URL back here:")
    print(f"  {url}")
    redirect_response = input("Callback URL: ")
    return extract_code_from_redirect(redirect_response, expected_state=state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Request a new DigiKey access token and write it to a token file"
    )
    parser.add_argument("--user", "-u", required=True, help="DigiKey Client ID")
    parser.add_argument("--secret", "-s", required=True, help="DigiKey Client secret")
    parser.add_argument(
        "--output", "-o", default=".token", help="Token output file name"
    )
    args = parser.parse_args(argv)
    try:
        code = get_auth_code(args.user, args.secret)
        token = exchange_code(args.user, args.secret, code)
        save_token(args.output, token)
    except (AuthError, AuthRequired) as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        if exc.details:
            print(f"  {exc.details}", file=sys.stderr)
        return 1
    print(f"Token saved to {args.output}")
    print(f"  access token expires in {max(0, int(token['expires_by']) - _now())} s")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
