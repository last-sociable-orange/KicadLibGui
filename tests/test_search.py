"""Search service and HTTP error-mapping tests (no network)."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests
from conftest import make_payload

import digikey_auth
import digikey_search
from kicad_core.errors import (
    AuthRequired,
    NetworkError,
    ParseError,
    RateLimitError,
    SearchError,
)
from services.search_service import SearchService


class FakeAuth:
    def __init__(self, path):
        self.token_path = path
        self.refresh_calls = 0

    def ensure_token(self, *, force_refresh=False, timeout=30):
        self.refresh_calls += 1
        if force_refresh:
            return {"access_token": "new"}
        return {"access_token": "old"}


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.post = Mock(side_effect=self._post)

    def _post(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


def response(status=200, payload=None, text="", headers=None):
    item = Mock()
    item.status_code = status
    item.text = text
    item.headers = headers or {}
    if payload is None:
        item.json = Mock(side_effect=ValueError("no json"))
    else:
        item.json = Mock(return_value=payload)
    return item


@pytest.fixture(autouse=True)
def token(monkeypatch, workdir):
    path = workdir / "token.json"
    digikey_auth.save_token(path, {
        "client_id": "client",
        "client_secret": "secret",
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_by": 9999999999,
        "refresh_token_expires_by": 9999999999,
    })
    monkeypatch.setattr(
        digikey_auth, "ensure_token", lambda *args, **kwargs: digikey_auth.load_token(path)
    )
    return path


def test_search_rejects_empty_query(workdir):
    service = SearchService(FakeAuth(workdir / "token.json"))
    with pytest.raises(SearchError):
        service.search("   ")


def test_search_parses_products(workdir):
    auth = FakeAuth(workdir / "token.json")
    service = SearchService(auth, search_fn=lambda *a, **k: {"Products": [make_payload("P1")]})
    products = service.search("P1")
    assert len(products) == 1
    assert products[0].mpn == "P1"
    assert auth.refresh_calls == 0


def test_search_refreshes_once_after_401(workdir):
    auth = FakeAuth(workdir / "token.json")
    calls = []

    def search_fn(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise AuthRequired("expired")
        return {"Products": [make_payload("P1")]}

    service = SearchService(auth, search_fn=search_fn)
    products = service.search("P1")
    assert len(products) == 1
    assert len(calls) == 2
    assert auth.refresh_calls == 1


def test_search_gives_up_after_second_401(workdir):
    auth = FakeAuth(workdir / "token.json")

    def search_fn(*args, **kwargs):
        raise AuthRequired("expired")

    service = SearchService(auth, search_fn=search_fn)
    with pytest.raises(AuthRequired):
        service.search("P1")


def test_search_maps_malformed_payload_to_parse_error(workdir):
    service = SearchService(
        FakeAuth(workdir / "token.json"),
        search_fn=lambda *a, **k: {"unexpected": True},
    )
    with pytest.raises(ParseError):
        service.search("P1")


def test_http_200_returns_payload():
    payload = {"Products": [make_payload("P1")]}
    result = digikey_search.digikey_search(
        "P1", token_file="ignored", session=FakeSession(response(payload=payload))
    )
    assert result == payload


def test_http_403_message():
    session = FakeSession(response(403, text="forbidden"))
    with pytest.raises(SearchError) as excinfo:
        digikey_search.digikey_search("P1", session=session)
    assert "scopes" in str(excinfo.value)


def test_http_429_retry_after():
    session = FakeSession(response(429, headers={"Retry-After": "12"}))
    with pytest.raises(RateLimitError) as excinfo:
        digikey_search.digikey_search("P1", session=session)
    assert excinfo.value.retry_after == 12
    assert "12" in str(excinfo.value)


def test_http_5xx_message():
    session = FakeSession(response(503, text="down"))
    with pytest.raises(SearchError) as excinfo:
        digikey_search.digikey_search("P1", session=session)
    assert "temporarily unavailable" in str(excinfo.value)


def test_invalid_json():
    session = FakeSession(response(200, payload=None, text="not json"))
    with pytest.raises(ParseError):
        digikey_search.digikey_search("P1", session=session)


def test_timeout_maps_to_network_error():
    session = FakeSession(error=requests.Timeout("slow"))
    with pytest.raises(NetworkError):
        digikey_search.digikey_search("P1", session=session)


def test_connection_error_maps_to_network_error():
    session = FakeSession(error=requests.ConnectionError("offline"))
    with pytest.raises(NetworkError):
        digikey_search.digikey_search("P1", session=session)


def test_empty_keywords_rejected():
    with pytest.raises(SearchError):
        digikey_search.digikey_search("  ", session=FakeSession(response(payload={})))
