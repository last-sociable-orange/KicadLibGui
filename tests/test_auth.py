"""Authentication helper tests (offline)."""

from __future__ import annotations

import json
import os
import stat
import time

import pytest

import digikey_auth
from kicad_core.errors import AuthError, AuthRequired
from services.auth_service import AuthService


def token_dict(now: int, *, access_in: int = 3600, refresh_in: int = 86400) -> dict:
    return {
        "client_id": "client",
        "client_secret": "secret",
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_by": now + access_in,
        "refresh_token_expires_by": now + refresh_in,
    }


def test_save_and_load_roundtrip(workdir):
    path = workdir / "token.json"
    token = token_dict(int(time.time()))
    digikey_auth.save_token(path, token)
    loaded = digikey_auth.load_token(path)
    assert loaded == token
    assert not list(path.parent.glob("*.tmp"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_missing_token_requires_auth(workdir):
    with pytest.raises(AuthRequired):
        digikey_auth.load_token(workdir / "missing.json")


def test_load_corrupt_token(workdir):
    path = workdir / "token.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(AuthError):
        digikey_auth.load_token(path)


def test_load_incomplete_token(workdir):
    path = workdir / "token.json"
    path.write_text(json.dumps({"access_token": "x"}), encoding="utf-8")
    with pytest.raises(AuthError):
        digikey_auth.load_token(path)


def test_token_status():
    now = 1_000_000
    status = digikey_auth.token_status(token_dict(now), now=now)
    assert status.present and status.access_valid and status.refresh_valid
    assert status.days_remaining == 1
    soon = digikey_auth.token_status(token_dict(now, access_in=10), now=now)
    assert not soon.access_valid
    expired = digikey_auth.token_status(token_dict(now, access_in=-10, refresh_in=-10), now=now)
    assert not expired.refresh_valid
    assert digikey_auth.token_status(None).summary == "Not signed in"


def test_build_authorization_url():
    url = digikey_auth.build_authorization_url("client id", state="abc")
    assert url.startswith(digikey_auth.AUTHORIZATION_BASE_URL)
    assert "response_type=code" in url
    assert "state=abc" in url
    assert "redirect_uri=" in url
    with pytest.raises(AuthError):
        digikey_auth.build_authorization_url("  ")


def test_extract_code_from_redirect():
    state = "expected"
    url = "https://localhost:8000/oauth2/callback?code=abc123&state=expected"
    assert digikey_auth.extract_code_from_redirect(url, expected_state=state) == "abc123"
    assert digikey_auth.extract_code_from_redirect(url) == "abc123"
    # Missing state is tolerated per the plan.
    assert digikey_auth.extract_code_from_redirect(
        "https://localhost:8000/oauth2/callback?code=abc123", expected_state=state
    ) == "abc123"
    with pytest.raises(AuthError):
        digikey_auth.extract_code_from_redirect(
            "https://localhost:8000/oauth2/callback?code=abc123&state=other",
            expected_state=state,
        )
    with pytest.raises(AuthError):
        digikey_auth.extract_code_from_redirect("https://localhost:8000/nothing")
    with pytest.raises(AuthError):
        digikey_auth.extract_code_from_redirect("?error=access_denied")
    assert digikey_auth.extract_code_from_redirect("bare-code") == "bare-code"


def test_exchange_code(monkeypatch, workdir):
    captured = {}

    def fake_post(data, timeout):
        captured.update(data)
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 1800,
            "refresh_token_expires_in": 7776000,
        }

    monkeypatch.setattr(digikey_auth, "_post_token_request", fake_post)
    token = digikey_auth.exchange_code("client", "secret", "code", now=1000)
    assert captured["grant_type"] == "authorization_code"
    assert token["access_token"] == "new-access"
    assert token["expires_by"] == 2800
    assert token["refresh_token_expires_by"] == 7777000
    assert token["client_id"] == "client"


def test_ensure_token_returns_valid_token(workdir, monkeypatch):
    path = workdir / "token.json"
    now = int(time.time())
    digikey_auth.save_token(path, token_dict(now))
    called = []
    monkeypatch.setattr(
        digikey_auth, "refresh_token_request",
        lambda *args, **kwargs: called.append(True),
    )
    token = digikey_auth.ensure_token(path)
    assert token["access_token"] == "access"
    assert called == []


def test_ensure_token_refreshes_and_rewrites(workdir, monkeypatch):
    path = workdir / "token.json"
    now = int(time.time())
    digikey_auth.save_token(path, token_dict(now, access_in=10))
    new_token = token_dict(now, access_in=1800)
    new_token["access_token"] = "refreshed"
    monkeypatch.setattr(
        digikey_auth, "refresh_token_request",
        lambda *args, **kwargs: (new_token, 1800),
    )
    result = digikey_auth.ensure_token(path)
    assert result["access_token"] == "refreshed"
    assert digikey_auth.load_token(path)["access_token"] == "refreshed"


def test_ensure_token_requires_sign_in_when_refresh_expired(workdir):
    path = workdir / "token.json"
    now = int(time.time())
    digikey_auth.save_token(path, token_dict(now, access_in=-10, refresh_in=-10))
    with pytest.raises(AuthRequired):
        digikey_auth.ensure_token(path)


def test_auth_service_status_and_clear(workdir):
    path = workdir / "token.json"
    service = AuthService(path)
    assert not service.status().present
    assert service.summary() == "Not signed in"
    digikey_auth.save_token(path, token_dict(int(time.time())))
    assert service.status().present
    assert service.credentials() == ("client", "secret")
    service.clear()
    assert not path.exists()
    assert not path.with_name(path.name + ".lock").exists()


def test_auth_service_imports_legacy_token(workdir):
    source = workdir / ".token"
    destination = workdir / "token.json"
    digikey_auth.save_token(source, token_dict(int(time.time())))
    AuthService(destination).import_legacy(source)
    assert destination.exists()
    assert digikey_auth.load_token(destination)["client_id"] == "client"
